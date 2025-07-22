# phorest_pipeline/syncer/logic.py
import shutil
import signal
import time
from pathlib import Path

from phorest_pipeline.shared.config import (
    BACKUP_DIR,
    DATA_DIR,
    ENABLE_SYNCER,
    FLAG_DIR,
    METADATA_FILENAME,
    REMOTE_ROOT_DIR,
    RESULTS_DIR,
    SYNC_INTERVAL,
    settings,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import (
    load_metadata_with_lock,
    lock_and_manage_file,
    update_metadata_manifest_entry,
    update_service_status,
)
from phorest_pipeline.shared.states import SyncerState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="syncer.log")

POLL_INTERVAL = SYNC_INTERVAL / 20 if SYNC_INTERVAL > (5 * 20) else 5

REMOTE_DATA_DIR = Path(REMOTE_ROOT_DIR, DATA_DIR.name)
REMOTE_RESULTS_DIR = Path(REMOTE_ROOT_DIR, RESULTS_DIR.name)
REMOTE_BACKUP_DIR = Path(REMOTE_ROOT_DIR, BACKUP_DIR.name)

SCRIPT_NAME = 'phorest-syncer'


def sync_archived_backups():
    """
    Moves all files from the local storage directory to the remote directory.
    """
    logger.info("Syncing archived backups...")
    if not BACKUP_DIR.exists():
        return

    REMOTE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    for item in BACKUP_DIR.iterdir():
        if item.is_file():
            try:
                shutil.move(str(item), str(REMOTE_BACKUP_DIR))
                logger.debug(f"Moved {item.name} to remote directory.")
            except Exception as e:
                logger.error(f"Failed to move {item.name}: {e}")


def sync_results_and_manifest():
    """
    Copies all files from local results directory to the remote directory.
    """
    logger.info("Copying results and manifest to remote directory...")

    # 1. List of file extensions to ignore
    ignored_extensions = [".lock", ".tmp"]

    # 2. Sync the results directory
    if RESULTS_DIR.exists():
        REMOTE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for item in RESULTS_DIR.iterdir():
            # Compare against `ignored_extension` list
            if item.is_file() and (item.suffix not in ignored_extensions):
                try:
                    with lock_and_manage_file(item):
                        shutil.copy2(str(item), str(REMOTE_RESULTS_DIR))
                    logger.debug(f"Copied results file: {item.name}")
                except Exception as e:
                    logger.error(f"Failed to copy {item.name}: {e}")

    # 3. Sync data manifest
    manifest_path = Path(DATA_DIR, METADATA_FILENAME)
    if manifest_path.exists():
        REMOTE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with lock_and_manage_file(manifest_path):
                shutil.copy2(str(manifest_path), str(REMOTE_DATA_DIR))
            logger.debug(f"Copied manifest file: {manifest_path.name}")
        except Exception as e:
            logger.error(f"Failed to copy manifest file: {manifest_path.name}: {e}")


def sync_processed_images():
    """
    Finds all processed images in the local storage directory and moves them to the remote directory.
    """
    logger.info("Syncing processed images to remote directory...")

    # 1. Find images to move
    manifest_data = load_metadata_with_lock(Path(DATA_DIR, METADATA_FILENAME))
    images_to_move = []
    indices_to_update = []
    for index, entry in enumerate(manifest_data):
        if (
            entry.get("processing_status") == "processed"
            and not entry.get("image_synced", False)
            and entry.get("camera_data", {}).get("filename")
        ):
            filepath = Path(DATA_DIR, entry["camera_data"]["filename"])
            if filepath.exists():
                images_to_move.append(filepath)
                indices_to_update.append(index)

    if not images_to_move:
        logger.info("No processed images to sync.")
        return

    # 2. Move images
    REMOTE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    moved_count = 0
    for image_path in images_to_move:
        try:
            shutil.move(str(image_path), str(REMOTE_DATA_DIR))
            logger.debug(f"Moved image: {image_path.name}")
            moved_count += 1
        except Exception as e:
            logger.error(f"Failed to move image {image_path.name}: {e}")
            # If moving failed DO NOT mark as synced
            failed_index = images_to_move.index(image_path)
            indices_to_update.pop(failed_index)

    # 3. Update manifest
    if indices_to_update:
        logger.info(f"Updating manifest for {len(indices_to_update)} images.")
        update_metadata_manifest_entry(
            Path(DATA_DIR, METADATA_FILENAME),
            indices_to_update,
            image_synced=True,
            new_filepath=REMOTE_DATA_DIR.resolve().as_posix(),
        )


class Syncer:
    """Encapsulates the state and logic for the file synchroniser."""

    def __init__(self):
        self.shutdown_requested = False
        self.current_state = SyncerState.IDLE
        self.next_run_time = 0

        # Register the signal handler
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, _signum, _frame):
        """Signal handler to initiate a graceful shutdown"""
        if not self.shutdown_requested:
            logger.info("Shutdown signal received. Finishing current cycle before stopping...")
            self.shutdown_requested = True

    def _perform_sync_cycle(self):
        """State machin logic for the syncer."""

        if settings is None:
            logger.debug("Configuration error. Halting.")
            time.sleep(POLL_INTERVAL * 5)
            self.current_state = SyncerState.FATAL_ERROR

        match self.current_state:
            case SyncerState.IDLE:
                logger.debug("IDLE -> WAITING_TO_RUN")
                self.next_run_time = time.monotonic() + SYNC_INTERVAL
                logger.debug(f"Will wait for {SYNC_INTERVAL} seconds until next cycle...")
                self.current_state = SyncerState.WAITING_TO_RUN

            case SyncerState.WAITING_TO_RUN:
                now = time.monotonic()
                if now >= self.next_run_time:
                    logger.debug("WAITING_TO_RUN -> SYNCING_FILES")
                    self.current_state = SyncerState.SYNCING_FILES
                else:
                    for _ in range(int(POLL_INTERVAL)):
                        if self.shutdown_requested:
                            return
                        time.sleep(1)

            case SyncerState.SYNCING_FILES:
                logger.info("--- Starting Sync Cycle ---")
                try:
                    sync_archived_backups()
                    sync_results_and_manifest()
                    sync_processed_images()
                    logger.info("--- Sync Cycle Finished ---")
                except Exception as e:
                    logger.error(f"Error during sync cycle: {e}")

                self.current_state = SyncerState.IDLE

            case SyncerState.FATAL_ERROR:
                logger.error("[FATAL ERROR] Shutting down syncer.")
                time.sleep(10)  # Prevent busy-looping in fatal state

    def run(self):
        """Main loop for the syncer process."""
        logger.info("--- Starting Syncer Process ---")
        print("--- Starting Syncer Process ---")

        if settings is None:
            logger.debug("Configuration error. Halting.")
            return

        if not ENABLE_SYNCER:
            logger.info("Syncer is disabled in config. Exiting.")
            return

        try:
            while not self.shutdown_requested:
                self._perform_sync_cycle()

                # After a cycle is complete, send a heartbeat.
                update_service_status(SCRIPT_NAME, heartbeat=True)

                time.sleep(0.1)  # Sleep to avoid busy waiting
        except Exception as e:
            logger.critical(f"UNEXPECTED ERROR in main loop: {e}", exc_info=True)
        finally:
            logger.info("--- Syncer Stopped ---")
            print("--- Syncer Stopped ---")


def run_syncer():
    """Main entry point to create and run a Synchroniser instanace."""
    sync = Syncer()
    sync.run()
