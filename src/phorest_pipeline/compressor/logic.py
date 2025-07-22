# phorest_pipeline/compressor/logic.py
import gzip
import shutil
import signal
import time
from pathlib import Path

from phorest_pipeline.shared.config import (
    COMPRESSOR_INTERVAL,
    DATA_DIR,
    ENABLE_COMPRESSOR,
    METADATA_FILENAME,
    settings,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import (
    load_metadata_with_lock,
    update_metadata_manifest_entry,
    update_service_status,
)
from phorest_pipeline.shared.states import CompressorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="compressor.log")

SCRIPT_NAME = "phorest-compressor"

POLL_INTERVAL = COMPRESSOR_INTERVAL / 20 if COMPRESSOR_INTERVAL > (5 * 20) else 5


def find_entries_to_compress(metadata_list: list) -> list[tuple[int, dict]]:
    """
    Finds all entries that have been processed but not yet compressed.
    This is universal for all image types but avoids re-compressing .gz files.
    """
    entries_to_compress = []
    for index, entry in enumerate(metadata_list):
        camera_data = entry.get("camera_data")
        if (
            entry.get("processing_status", "pending") == "processed"
            and not entry.get("compression_attempted", False)
            and camera_data
            and camera_data.get("filename")
            and Path(camera_data["filename"]).suffix != ".gz"
        ):
            filepath = Path(camera_data["filepath"], camera_data["filename"])
            if filepath.exists():
                entries_to_compress.append((index, entry))
    return entries_to_compress


class Compressor:
    """Encapsulates the state and logic for the file compressor."""

    def __init__(self):
        # All state is now managed by the instance
        self.shutdown_requested = False
        self.current_state = CompressorState.IDLE
        self.next_run_time = 0
        self.entries_to_process = []  # To hold the batch of work

        # Register signal handlers
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, _signum, _frame):
        """Signal handler to initiate a graceful shutdown"""
        if not self.shutdown_requested:
            logger.info("Shutdown signal received. Finishing current cycle before stopping...")
            self.shutdown_requested = True

    def _perform_compression_cycle(self):
        """State machine logic for the compressor."""

        if settings is None:
            logger.debug("Configuration error. Halting.")
            self.current_state = CompressorState.FATAL_ERROR
            return

        match self.current_state:
            case CompressorState.IDLE:
                logger.debug("IDLE -> CHECKING")
                self.next_run_time = time.monotonic() + COMPRESSOR_INTERVAL
                self.current_state = CompressorState.CHECKING

            case CompressorState.CHECKING:
                logger.info("--- Checking Manifest for Compression Work ---")
                manifest_data = load_metadata_with_lock(Path(DATA_DIR, METADATA_FILENAME))
                self.entries_to_process = find_entries_to_compress(manifest_data)

                if self.entries_to_process:
                    logger.info(
                        f"Found a batch of {len(self.entries_to_process)} files to compress."
                    )
                    self.current_state = CompressorState.COMPRESSING_IMAGES
                else:
                    logger.info("No entries found requiring compression.")
                    logger.debug(
                        f"Will wait for {COMPRESSOR_INTERVAL} seconds until next check..."
                    )
                    self.current_state = CompressorState.WAITING_TO_RUN

            case CompressorState.WAITING_TO_RUN:
                now = time.monotonic()
                if now >= self.next_run_time:
                    self.current_state = CompressorState.IDLE
                else:
                    for _ in range(int(POLL_INTERVAL)):
                        if self.shutdown_requested:
                            return
                        time.sleep(1)

            case CompressorState.COMPRESSING_IMAGES:
                logger.info(
                    f"--- Starting Image Compression for batch of {len(self.entries_to_process)} files ---"
                )

                updates_for_manifest = []
                for entry_index, entry_data in self.entries_to_process:
                    try:
                        camera_data = entry_data["camera_data"]
                        original_filepath = Path(camera_data["filepath"], camera_data["filename"])

                        gzipped_filename = original_filepath.name + ".gz"
                        gzipped_filepath = original_filepath.with_name(gzipped_filename)

                        logger.debug(f"gzipping {original_filepath} to {gzipped_filepath}...")
                        with (
                            original_filepath.open("rb") as f_in,
                            gzip.open(gzipped_filepath, "wb") as f_out,
                        ):
                            shutil.copyfileobj(f_in, f_out)

                        original_filepath.unlink()

                        updates_for_manifest.append(
                            {
                                "index": entry_index,
                                "new_filename": gzipped_filename,
                            }
                        )
                        logger.info(f"Successfully gzipped {original_filepath.name}.")
                    except Exception:
                        logger.error(f"Failed to gzip {original_filepath.name}.", exc_info=True)
                        updates_for_manifest.append(
                            {
                                "index": entry_index,
                                "new_filename": None,
                            }
                        )

                # Update manifest
                if updates_for_manifest:
                    try:
                        logger.debug(
                            f"Updating manifest for {len(updates_for_manifest)} entries..."
                        )
                        indices = [item["index"] for item in updates_for_manifest]
                        filenames = [item["new_filename"] for item in updates_for_manifest]

                        update_metadata_manifest_entry(
                            Path(DATA_DIR, METADATA_FILENAME),
                            entry_index=indices,
                            compression_attempted=True,
                            new_filename=filenames,
                        )
                        logger.info("Batch manifest update successful.")
                    except Exception as e:
                        logger.error(
                            f"CRITICAL: Failed to update manifest after compression batch: {e}",
                            exc_info=True,
                        )
                        self.current_state = CompressorState.WAITING_TO_RUN
                        return

                logger.debug("COMPRESSING_FILES -> CHECKING (for more work)")
                self.current_state = CompressorState.CHECKING
                time.sleep(0.1)

            case CompressorState.FATAL_ERROR:
                logger.error("[FATAL ERROR] Shutting down compressor.")
                time.sleep(10)  # Prevent busy-looping in fatal state

    def run(self):
        """Main loop for the compressor process."""
        logger.info("--- Starting Compressor ---")
        print("--- Starting Compressor ---")

        if settings is None:
            logger.debug("Configuration error. Exiting.")
            return

        if not ENABLE_COMPRESSOR:
            logger.info("Compressor is disabled in config. Exiting.")
            return

        try:
            while not self.shutdown_requested:
                self._perform_compression_cycle()

                # After a cycle is complete, send a heartbeat.
                update_service_status(SCRIPT_NAME, heartbeat=True)

                time.sleep(0.1)
        except Exception as e:
            logger.critical(f"UNEXPECTED ERROR in main loop: {e}", exc_info=True)
        finally:
            logger.info("--- Compressor Stopped ---")
            print("--- Compressor Stopped ---")


def run_compressor():
    """Main entry point to create and run a Compressor instanace."""
    compressor = Compressor()
    compressor.run()
