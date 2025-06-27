# phorest_pipeline/shared/metadata_manager.py
import datetime
import json
import fcntl # For file locking (Unix/Linux specific)
import os
import shutil
from pathlib import Path
from contextlib import contextmanager

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


@contextmanager
def lock_and_manage_file(file_path: Path):
    """
    A context manager to safely lock a file path for an arbitrary operation.
    Usage:
        with lock_and_manage_file(my_path):
            # ... perform file operations here ...
    """
    lock_fd = None
    try:
        lock_fd = _acquire_lock(file_path)
        logger.debug(f"[METADATA] [CONTEXT_LOCK] Acquired lock for {file_path.name}")
        yield  # Passes control back to the 'with' block
    finally:
        _release_lock(lock_fd, file_path.name)
        logger.debug(f"[METADATA] [CONTEXT_LOCK] Released lock for {file_path.name}")
    

def add_entry(
    data_dir: Path, metadata_filename: Path, camera_meta: dict | None, temps_meta: dict | None
):
    """
    Adds a new combined entry to the processing manifest, protected by a file lock.
    Used by the Collector.
    """
    manifest_path = Path(data_dir, metadata_filename)

    try:
        with lock_and_manage_file(manifest_path):
            logger.info('[METADATA] [ADD] Updating processing manifest (locked section)...')

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
                'compression_attempted': False,
            }

            metadata_list.append(new_manifest_entry)
            _save_metadata(data_dir, metadata_filename, metadata_list) # Safe to save under lock

            img_name = camera_meta.get('filename') if camera_meta else 'N/A'
            status_log = 'FAILED' if overall_collection_error else 'OK'
            logger.info(f'[METADATA] [ADD] Added entry to manifest: Status={status_log}, Image={img_name}')
    except Exception as e:
        logger.error(f"[METADATA] [ADD] Error in add_entry (manifest write): {e}")
        raise # Re-raise to propagate error to collector


def append_metadata(data_dir: Path, metadata_filename: Path, metadata_to_append: dict | list[dict]):
    """
    Appends a new entry to a specified metadata file (e.g., processing_results.json),
    protected by a file lock specific to that file.
    Used by the Processor for its results file.
    """
    target_file_path = Path(data_dir, metadata_filename) # Full path to the target file

    try:
        with lock_and_manage_file(target_file_path):
            entries_to_add = metadata_to_append if isinstance(metadata_to_append, list) else [metadata_to_append]

            if not entries_to_add:
                logger.info(f'[METADATA] [APPEND] append called with no entries for {metadata_filename.name}. Returning.')
                return

            logger.info(f'[METADATA] [APPEND] Appending {len(entries_to_add)} entries to {metadata_filename.name} (locked section)...')

            metadata_list = _load_metadata(data_dir, metadata_filename) # Safe to read under lock
            metadata_list.extend(entries_to_add)
            _save_metadata(data_dir, metadata_filename, metadata_list)
            logger.info(f'[METADATA] [APPEND] Successfully appended {len(entries_to_add)} entries to {metadata_filename.name}.')
    except Exception as e:
        logger.error(f"[METADATA] [APPEND] Error in append_metadata ({metadata_filename.name} write): {e}")
        raise # Re-raise to propagate error


def update_metadata_manifest_entry(
    data_dir: Path,
    metadata_filename: Path,
    entry_index: int | list[int],
    status: str | list[str] | None = None,
    processing_timestamp_iso: str | list[str] | None = None,
    processing_error: bool | list[bool] | None = None,
    processing_error_msg: str | list[str] | None = None,
    compression_attempted: bool = False,
    new_filename: str | None = None,
):
    """
    Updates status and results for one or more entries in the processing manifest.
    If 'entry_index' is a list, data arguments (e.g., 'status', 'processing_error_msg')
    can also be lists of the same length to apply unique values to each entry.
    If data arguments are single values, they are applied to all specified entries.
    """
    manifest_path = Path(data_dir, metadata_filename)

    try:
        with lock_and_manage_file(manifest_path):
            logger.info(f'[METADATA] [UPDATE] Updating manifest entry {entry_index} status (locked section)...')

            metadata_list = _load_metadata(data_dir, metadata_filename) # Safe to read under lock

            indices = entry_index if isinstance(entry_index, list) else [entry_index]
            num_indices = len(indices)

            def get_value_for_index(arg, i):
                if isinstance(arg, list):
                    if len(arg) != num_indices:
                        logger.warning(f"[METADATA] [UPDATE] Argument list length mismatch for entry {indices[i]}. Using None.")
                        return None
                    return arg[i]
                return arg
            
            for i, index_to_update in enumerate(indices):
                if 0 <= index_to_update < len(metadata_list):
                    entry = metadata_list[index_to_update]

                    current_status = get_value_for_index(status, i)
                    if current_status is not None:
                        entry['processing_status'] = current_status
                    
                    current_ts = get_value_for_index(processing_timestamp_iso, i)
                    if current_ts is not None:
                        entry['processing_timestamp_iso'] = current_ts
                
                    current_err = get_value_for_index(processing_error, i)
                    if current_err is not None:
                        entry['processing_error'] = current_err

                    current_err_msg = get_value_for_index(processing_error_msg, i)
                    if current_err_msg is not None:
                        entry['processing_error_msg'] = current_err_msg

                    if compression_attempted:
                        entry['compression_attempted'] = compression_attempted

                    if new_filename:
                        if 'camera_data' in entry and entry['camera_data']:
                            entry['camera_data']['filename'] = new_filename
                else:
                    logger.warning(
                        f'[METADATA] [UPDATE] Attempted to update non-existent manifest entry at index {index_to_update}. '
                        f'This can happen if the manifest was backed up and cleared while an item was being processed. '
                        f'The results for this entry will be discarded.'
                    )
                
            _save_metadata(data_dir, metadata_filename, metadata_list)
            logger.info(f'[METADATA] [UPDATE] Batch update successful for {len(indices)} manifest entries.')

    except Exception as e:
        logger.error(f"[METADATA] [UPDATE] Error in update_manifest_entry_status: {e}")
        raise # Re-raise to propagate error


def load_metadata_with_lock(data_dir: Path, metadata_filename: Path) -> list:
    """
    Loads metadata from a JSON file using file locking for safety.
    Returns an empty list if the file does not exist or if there's a decoding error.
    """
    metadata_path = Path(data_dir, metadata_filename)

    try:
        with lock_and_manage_file(metadata_path):
            return _load_metadata(data_dir, metadata_filename)  # Safe to read under lock
    except Exception as e:
        logger.error(f"[METADATA] [LOAD] Error loading metadata with lock: {e}")
        raise # Re-raise to propagate error


def save_metadata_with_lock(data_dir: Path, metadata_filename: Path, metadata_list: list):
    """
    Saves results data to a JSON file using file locking and atomic write for safety.
    """
    metadata_path = Path(data_dir, metadata_filename)

    try:
        with lock_and_manage_file(metadata_path):
            _save_metadata(data_dir, metadata_filename, metadata_list)  # Safe to save under lock
    except Exception as e:
        logger.error(f"[METADATA] [SAVE] Error saving metadata with lock: {e}")
        raise # Re-raise to propagate error


def move_file_with_lock(source_dir: Path, source_filename: Path, destination_path: Path):
    """
    Safely moves a file using file locks.  This is an atomic operation
    that prevents race conditions with other processes.
    """
    source_path = Path(source_dir, source_filename)

    try:
        with lock_and_manage_file(source_path):
            logger.info(f"[METADATA] [MOVE] Moving {source_path.name} to {destination_path.name} (locked section)...")

            if not source_path.exists():
                logger.error(f"[METADATA] [MOVE] Cannot back up {source_path.name} as it does not exist. Skipping.")
                return
            
            destination_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure destination directory exists

            shutil.move(str(source_path), str(destination_path))
            logger.info(f"[METADATA] [MOVE] Successfully moved {source_path.name} to {destination_path.name}.")

            # Clean up any associated .tmp files
            temp_file_path = source_path.with_suffix(source_path.suffix + '.tmp')
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                    logger.info(f"[METADATA] [MOVE] Removed temporary file {temp_file_path.name} after move.")
                except OSError as e:
                    logger.error(f"[METADATA] [MOVE] Failed to remove temporary file {temp_file_path.name}: {e}")

    except Exception as e:
        logger.error(f"[METADATA] [MOVE] An unexpect error occured while moving {source_path.name}: {e}")
        raise
