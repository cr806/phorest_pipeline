# phorest_pipeline/compressor/logic.py
import time
import gzip
import shutil
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
)
from phorest_pipeline.shared.states import CompressorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="compressor.log")

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
            entry.get("processing_status", 'pending') == "processed"
            and not entry.get("compression_attempted", False)
            and camera_data
            and camera_data.get("filename")
            and not Path(camera_data["filename"]).suffix == '.gx'
        ):
            filepath = Path(camera_data["filepath"], camera_data["filename"])
            if filepath.exists():
                entries_to_compress.append((index, entry))
    return entries_to_compress


def perform_compression_cycle(current_state: CompressorState) -> CompressorState:
    """State machine logic for the compressor."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return current_state  # Consider a FATAL_ERROR state

    match current_state:
        case CompressorState.IDLE:
            logger.info("IDLE -> CHECKING")
            next_state = CompressorState.CHECKING
            global next_run_time
            next_run_time = time.monotonic() + COMPRESSOR_INTERVAL

        case CompressorState.CHECKING:
            logger.info("--- Checking Manifest for Compression Work ---")
            manifest_data = load_metadata_with_lock(DATA_DIR, METADATA_FILENAME)

            global entries_to_process # Store the batch
            entries_to_process = find_entries_to_compress(manifest_data)

            if entries_to_process:
                logger.info(
                    f"Found a batch of {len(entries_to_process)} files to compress."
                )
                next_state = CompressorState.COMPRESSING_IMAGES
            else:
                logger.info("No entries found requiring compression.")
                next_state = CompressorState.WAITING_TO_RUN
                logger.info(f"Will wait for {COMPRESSOR_INTERVAL} seconds until next check...")

        case CompressorState.COMPRESSING_IMAGES:
            logger.info(f"--- Starting Image Compression for batch of {len(entries_to_process)} files ---")

            updates_for_manifest = []
            for entry_index, entry_data in entries_to_process:
                try:
                    camera_data = entry_data["camera_data"]
                    original_filepath = Path(camera_data["filepath"], camera_data["filename"])

                    gzipped_filename = original_filepath.name + '.gz'
                    gzipped_filepath = original_filepath.with_name(gzipped_filename)

                    logger.info(f"gzipping {original_filepath} to {gzipped_filepath}...")
                    with original_filepath.open("rb") as f_in, gzip.open(gzipped_filepath, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    
                    original_filepath.unlink()

                    updates_for_manifest.append({
                        "index": entry_index,
                        "new_filename": gzipped_filename,
                    })
                    logger.info(f"Successfully gzipped {original_filepath.name}.")
                except Exception as e:
                    logger.error(f"Failed to gzip {original_filepath.name}.", exc_info=True)
                    updates_for_manifest.append({
                        "index": entry_index,
                        "new_filename": None,
                    })
            
            # Update manifest
            if updates_for_manifest:
                try:
                    logger.info(f"Updating manifest for {len(updates_for_manifest)} entries...")
                    indices = [item["index"] for item in updates_for_manifest]
                    filenames = [item["new_filename"] for item in updates_for_manifest]

                    update_metadata_manifest_entry(
                        DATA_DIR,
                        METADATA_FILENAME,
                        entry_index=indices,
                        compression_attempted=True,
                        new_filename=filenames
                    )
                    logger.info("Batch manifest update successful.")
                except Exception as e:
                    logger.error(f"CRITICAL: Failed to update manifest after compression batch: {e}", exc_info=True)
                    next_state = CompressorState.WAITING_TO_RUN
                    return next_state
            
            logger.info("COMPRESSING_FILES -> CHECKING (for more work)")
            next_state = CompressorState.CHECKING
            time.sleep(0.1)


        case CompressorState.WAITING_TO_RUN:
            time.sleep(POLL_INTERVAL)
            now = time.monotonic()
            if now >= next_run_time:
                next_state = CompressorState.IDLE

    return next_state


def run_compressor():
    """Main loop for the compressor process."""
    logger.info("--- Starting Compressor ---")
    print("--- Starting Compressor ---")
    if not ENABLE_COMPRESSOR:
        logger.info("Compressor is disabled in config. Exiting.")
        return

    current_state = CompressorState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0
    try:
        while True:
            current_state = perform_compression_cycle(current_state)
            if (
                current_state == CompressorState.IDLE
                or current_state == CompressorState.WAITING_TO_RUN
            ):
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        logger.info("--- Compressor Stopped ---")
        print("--- Compressor Stopped ---")
