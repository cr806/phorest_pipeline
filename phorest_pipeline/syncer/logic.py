# phorest_pipeline/syncer/logic.py
import time
import shutil
from pathlib import Path

from phorest_pipeline.shared.config import (
    BACKUP_DIR,
    DATA_DIR,
    REMOTE_ROOT_DIR,
    RESULTS_DIR,
    SYNC_INTERVAL,
    METADATA_FILENAME,
    settings,
)
from phorest_pipeline.shared.metadata_manager import (
    lock_and_manage_file,
    load_metadata_with_lock,
    update_metadata_manifest_entry,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.states import SyncerState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="syncer.log")

POLL_INTERVAL = SYNC_INTERVAL / 20 if SYNC_INTERVAL > (5 * 20) else 5

REMOTE_DATA_DIR = Path(REMOTE_ROOT_DIR, DATA_DIR.name)
REMOTE_RESULTS_DIR = Path(REMOTE_ROOT_DIR, RESULTS_DIR.name)
REMOTE_BACKUP_DIR = Path(REMOTE_ROOT_DIR, BACKUP_DIR.name)


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
                logger.info(f"Moved {item.name} to remote directory.")
            except Exception as e:
                logger.error(f"Failed to move {item.name}: {e}")


def sync_results_and_manifest():
    """
    Copies all files from local results directory to the remote directory.
    """
    logger.info("Copying results and manifest to remote directory...")

    if RESULTS_DIR.exists():
        REMOTE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for item in RESULTS_DIR.iterdir():
            if item.is_file():
                try:
                    with lock_and_manage_file(item):
                        shutil.copy2(str(item). str(Path(REMOTE_RESULTS_DIR)))
                    logger.info(f"Copied results file: {item.name}")
                except Exception as e:
                    logger.error(f"Failed to copy {item.name}: {e}")
    
    manifest_path = Path(DATA_DIR, METADATA_FILENAME)
    if manifest_path.exists():
        REMOTE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with lock_and_manage_file(manifest_path):
                shutil.copy2(str(manifest_path), str(REMOTE_DATA_DIR))
            logger.info(f"Copied manifest file: {manifest_path.name}")
        except Exception as e:
            logger.error(f"Failed to copy manifest file: {manifest_path.name}: {e}")


def sync_processed_images():
    """
    Finds all processed images in the local storage directory and moves them to the remote directory.
    """
    logger.info("Syncing processed images to remote directory...")

    # 1. Find images to move
    manifest_data = load_metadata_with_lock(DATA_DIR, METADATA_FILENAME)
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
            logger.info(f"Moved image: {image_path.name}")
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
            DATA_DIR,
            METADATA_FILENAME,
            indices_to_update,
            image_synced=True,
        )


def perform_sync_cycle(current_state: SyncerState) -> SyncerState:
    """State machin logic for the syncer."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return current_state  # FATAL_ERROR state ?

    match current_state:
        case SyncerState.IDLE:
            logger.info("IDLE -> WAITING_TO_RUN")
            next_state = SyncerState.WAITING_TO_RUN
            global next_run_time
            next_run_time = time.monotonic() + SYNC_INTERVAL
            logger.info(f"Will wait for {SYNC_INTERVAL} seconds until next cycle...")
        
        case SyncerState.WAITING_TO_RUN:
            now = time.monotonic()
            if now >= next_run_time:
                logger.info("WAITING_TO_RUN -> SYNCING_FILES")
                next_state = SyncerState.SYNCING_FILES
            else:
                time.sleep(POLL_INTERVAL)
        
        case SyncerState.SYNCING_FILES:
            logger.info("--- Starting Sync Cycle ---")
            try:
                sync_archived_backups()
                sync_results_and_manifest()
                sync_processed_images()
                logger.info("--- Sync Cycle Finished ---")
            except Exception as e:
                logger.error(f"Error during sync cycle: {e}")
            
            next_state = SyncerState.IDLE
    
    return next_state


def run_syncer():
    """Main loop for the syncer process."""
    logger.info("--- Starting Syncer Process ---")
    print("--- Starting Syncer Process ---")
    
    current_state = SyncerState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0
    try:
        while True:
            current_state = perform_sync_cycle(current_state)
            if current_state == SyncerState.IDLE:
                time.sleep(0.1)  # Sleep to avoid busy waiting
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        logger.info("--- Syncer Stopped ---")
        print("--- Syncer Stopped ---")