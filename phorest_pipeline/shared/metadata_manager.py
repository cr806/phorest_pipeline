# phorest_pipeline/shared/metadata_manager.py
import datetime
import json
import fcntl # For file locking (Unix/Linux specific)
import os
from pathlib import Path

from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='shared.log')

LOCK_FILE_SUFFIX = ".lock"


def _acquire_lock(file_path_for_locking: Path):
    """
    Acquires an exclusive lock on a lock file derived from the given file_path.
    Returns the file descriptor of the lock file. This is a blocking call.
    """
    lock_path = file_path_for_locking.with_suffix(file_path_for_locking.suffix + LOCK_FILE_SUFFIX)
    lock_file_fd = None # Initialize to None

    try:
        # Open with O_CREAT to create if it doesn't exist, O_RDWR for read/write
        # Using a separate lock file ensures we don't try to lock the actual data file
        # which is being replaced atomically.
        lock_file_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_file_fd, fcntl.LOCK_EX) # Exclusive lock (blocking)
        logger.debug(f"[METADATA] [LOCK] Acquired lock for {lock_path.name}")
        return lock_file_fd
    except OSError as e:
        logger.error(f"[METADATA] [LOCK] Failed to acquire lock for {lock_path.name}: {e}")
        # Ensure file descriptor is closed if lock acquisition fails
        if lock_file_fd is not None:
            os.close(lock_file_fd)
        raise # Re-raise the exception

def _release_lock(lock_file_fd: int | None, lock_path_name: str = "unknown"):
    """
    Releases the lock on the given file descriptor and closes it.
    """
    if lock_file_fd is not None:
        try:
            fcntl.flock(lock_file_fd, fcntl.LOCK_UN) # Unlock
            os.close(lock_file_fd)
            logger.debug(f"[METADATA] [LOCK] Released lock for {lock_path_name}")
        except OSError as e:
            logger.error(f"[METADATA] [LOCK] Error releasing or closing lock file descriptor for {lock_path_name}: {e}")


def _load_metadata(data_dir: Path, metadata_filename: Path) -> list:
    metadata_path = Path(data_dir, metadata_filename)
    if metadata_path.exists():
        try:
            with metadata_path.open('r') as f:
                content = f.read()
                if not content:
                    logger.warning(f'[METADATA] {metadata_path.name} is empty. Returning empty list.')
                    return []
                return json.loads(content)
        except json.JSONDecodeError:
            logger.error(f'[METADATA] Corrupt JSON in {metadata_path}. Returning empty list.')
            # Archive the corrupt file for debugging
            corrupt_backup_path = Path(metadata_path.parent, f"{metadata_path.stem}.corrupt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{metadata_path.suffix}")
            try:
                metadata_path.rename(corrupt_backup_path)
                logger.info(f"[METADATA] Moved corrupt file to {corrupt_backup_path.name}")
            except OSError as e:
                logger.error(f"[METADATA] Failed to move corrupt file {metadata_path.name}: {e}")
            return []
        except OSError as e:
            logger.error(f'[METADATA] Read error {metadata_path}: {e}. Returning empty list.')
            return []
    else:
        logger.error(f'[METADATA] {metadata_path.name} does not exist. Returning empty list.')
        return []


def _save_metadata(data_dir: Path, metadata_filename: Path, metadata_list: list):
    metadata_path = Path(data_dir, metadata_filename)
    temp_metadata_path = metadata_path.with_suffix(metadata_path.suffix + '.tmp')
    try:
        with temp_metadata_path.open('w') as f:
            json.dump(metadata_list, f, indent=4)
        temp_metadata_path.replace(metadata_path)
        logger.debug(f"[METADATA] Atomic write successful for {metadata_path.name}")
    except (OSError, TypeError) as e:
        logger.error(f'[METADATA] Save error {metadata_path}: {e}')
        if temp_metadata_path.exists():
            try:
                temp_metadata_path.unlink()
            except OSError:
                pass
        raise # Re-raise to propagate error


def add_entry(
    data_dir: Path, metadata_filename: Path, camera_meta: dict | None, temps_meta: dict | None
):
    """
    Adds a new combined entry to the processing manifest, protected by a file lock.
    Used by the Collector.
    """
    manifest_path = Path(data_dir, metadata_filename)
    lock_fd = None

    try:
        lock_fd = _acquire_lock(manifest_path)
        logger.info('[METADATA] Updating processing manifest (locked section)...')

        metadata_list = _load_metadata(data_dir, metadata_filename) # Safe to read under lock

        overall_collection_error = False
        error_messages = []
        if camera_meta and camera_meta.get('error_flag', False):
            overall_collection_error = True
            error_messages.append(f'Camera: {camera_meta.get("error_message", "Unknown error")}')
        if temps_meta and temps_meta.get('error_flag', False):
            overall_collection_error = True
            error_messages.append(f'Temps: {temps_meta.get("error_message", "Unknown error")}')

        new_manifest_entry = {
            'entry_timestamp_iso': datetime.datetime.now().isoformat(),
            'collection_error': overall_collection_error,
            'collection_error_msg': ' | '.join(error_messages) if error_messages else None,
            'camera_data': camera_meta,
            'temperature_data': temps_meta,
            'processing_status': 'pending', # This field will allow the lock to be released while processing happens
            'processing_timestamp_iso': None,
            'processing_error': False,
            'processing_error_msg': None,
            'image_analysis_results': None,
            'temperature_processing_results': None,
        }

        metadata_list.append(new_manifest_entry)
        _save_metadata(data_dir, metadata_filename, metadata_list) # Safe to save under lock

        img_name = camera_meta.get('filename') if camera_meta else 'N/A'
        status_log = 'FAILED' if overall_collection_error else 'OK'
        logger.info(f'[METADATA] Added entry to manifest: Status={status_log}, Image={img_name}')
    except Exception as e:
        logger.error(f"[METADATA] Error in add_entry (manifest write): {e}")
        raise # Re-raise to propagate error to collector
    finally:
        _release_lock(lock_fd, manifest_path.name) # Ensure lock is always released


def append_metadata(data_dir: Path, metadata_filename: Path, metadata_dict: dict):
    """
    Appends a new entry to a specified metadata file (e.g., processing_results.json),
    protected by a file lock specific to that file.
    Used by the Processor for its results file.
    """
    target_file_path = Path(data_dir, metadata_filename) # Full path to the target file
    lock_fd = None

    try:
        lock_fd = _acquire_lock(target_file_path)
        logger.info(f'[METADATA] Updating {metadata_filename.name} (locked section)...')

        metadata_list = _load_metadata(data_dir, metadata_filename) # Safe to read under lock
        metadata_list.append(metadata_dict)
        _save_metadata(data_dir, metadata_filename, metadata_list)
        logger.info(f'[METADATA] Appended entry to {metadata_filename.name}.')
    except Exception as e:
        logger.error(f"[METADATA] Error in append_metadata ({metadata_filename.name} write): {e}")
        raise # Re-raise to propagate error
    finally:
        _release_lock(lock_fd, target_file_path.name) # Ensure lock is always released


def update_metadata_manifest_entry(
    data_dir: Path,
    metadata_filename: Path,
    entry_index: int,
    new_status: str | None = None,
    processing_timestamp_iso: str | None = None,
    processing_error: bool = False,
    processing_error_msg: str | None = None,
    image_analysis_results: dict | None = None,
    temperature_processing_results: dict | None = None,
    compression_attempted: bool = False,
    new_filename: str | None = None,
):
    """
    Updates the status and results of a specific entry in the processing manifest,
    protected by a file lock. Used by the Processor for marking entries.
    """
    manifest_path = Path(data_dir, metadata_filename)
    lock_fd = None

    try:
        lock_fd = _acquire_lock(manifest_path)
        logger.info(f'[METADATA] Updating manifest entry {entry_index} status (locked section)...')

        metadata_list = _load_metadata(data_dir, metadata_filename) # Safe to read under lock

        if 0 <= entry_index < len(metadata_list):
            entry_to_update = metadata_list[entry_index]
            if new_status:
                entry_to_update['processing_status'] = new_status
            if processing_timestamp_iso:
                entry_to_update['processing_timestamp_iso'] = processing_timestamp_iso
            if processing_error:
                entry_to_update['processing_error'] = processing_error
            if processing_error_msg:
                entry_to_update['processing_error_msg'] = processing_error_msg
            if image_analysis_results:
                entry_to_update['image_analysis_results'] = image_analysis_results
            if temperature_processing_results:
                entry_to_update['temperature_processing_results'] = temperature_processing_results
            if compression_attempted:
                entry_to_update['compression_attempted'] = compression_attempted
            if new_filename:
                if 'camera_data' in entry_to_update and entry_to_update['camera_data']:
                    entry_to_update['camera_data']['filename'] = new_filename

            _save_metadata(data_dir, metadata_filename, metadata_list) # Safe to save under lock
            logger.info(f'[METADATA] Manifest entry {entry_index} updated to status: {new_status}.')
        else:
            logger.warning(f'[METADATA] Attempted to update non-existent manifest entry at index {entry_index}.')
    except Exception as e:
        logger.error(f"[METADATA] Error in update_manifest_entry_status: {e}")
        raise # Re-raise to propagate error
    finally:
        _release_lock(lock_fd, manifest_path.name) # Ensure lock is always released


def load_metadata_with_lock(data_dir: Path, metadata_filename: Path) -> list:
    """
    Loads metadata from a JSON file using file locking for safety.
    Returns an empty list if the file does not exist or if there's a decoding error.
    """
    metadata_path = Path(data_dir, metadata_filename)
    lock_fd = None
    loaded_data = []

    try:
        lock_fd = _acquire_lock(metadata_path)
        loaded_data = _load_metadata(data_dir, metadata_filename)  # Safe to read under lock
    except Exception as e:
        logger.error(f"[METADATA] Error loading metadata with lock: {e}")
        raise # Re-raise to propagate error
    finally:
        _release_lock(lock_fd, metadata_path.name)
    
    return loaded_data


def save_metadata_with_lock(data_dir: Path, metadata_filename: Path, metadata_list: list):
    """
    Saves results data to a JSON file using file locking and atomic write for safety.
    """
    metadata_path = Path(data_dir, metadata_filename)
    lock_fd = None

    try:
        lock_fd = _acquire_lock(metadata_path)
        _save_metadata(data_dir, metadata_filename, metadata_list)  # Safe to save under lock
    except Exception as e:
        logger.error(f"[METADATA] Error saving metadata with lock: {e}")
        raise # Re-raise to propagate error
    finally:
        _release_lock(lock_fd, metadata_path.name)  # Ensure lock is always released