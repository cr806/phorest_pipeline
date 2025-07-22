# phorest_pipeline/shared/metadata_manager.py
import datetime
import fcntl  # For file locking (Unix/Linux specific)
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from phorest_pipeline.shared.config import STATUS_FILENAME, FLAG_DIR
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="shared.log")

LOCK_FILE_SUFFIX = ".lock"


def _acquire_lock(file_path_for_locking: Path):
    """
    Acquires an exclusive lock on a lock file derived from the given file_path.
    Returns the file descriptor of the lock file. This is a blocking call.
    """
    lock_path = file_path_for_locking.with_suffix(file_path_for_locking.suffix + LOCK_FILE_SUFFIX)
    lock_file_fd = None  # Initialize to None

    try:
        # Open with O_CREAT to create if it doesn't exist, O_RDWR for read/write
        # Using a separate lock file ensures we don't try to lock the actual data file
        # which is being replaced atomically.
        lock_file_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_file_fd, fcntl.LOCK_EX)  # Exclusive lock (blocking)
        logger.debug(f"[METADATA] [LOCK] Acquired lock for {lock_path.name}")
        return lock_file_fd
    except OSError as e:
        logger.error(f"[METADATA] [LOCK] Failed to acquire lock for {lock_path.name}: {e}")
        # Ensure file descriptor is closed if lock acquisition fails
        if lock_file_fd is not None:
            os.close(lock_file_fd)
        raise  # Re-raise the exception


def _release_lock(lock_file_fd: int | None, lock_path_name: str = "unknown"):
    """
    Releases the lock on the given file descriptor and closes it.
    """
    if lock_file_fd is not None:
        try:
            fcntl.flock(lock_file_fd, fcntl.LOCK_UN)  # Unlock
            os.close(lock_file_fd)
            logger.debug(f"[METADATA] [LOCK] Released lock for {lock_path_name}")
        except OSError as e:
            logger.error(
                f"[METADATA] [LOCK] Error releasing or closing lock file descriptor for {lock_path_name}: {e}"
            )


def _load_metadata(metadata_path: Path) -> list:
    """
    Loads metadata from a file. Handles both standard multi-line JSON (.json)
    and JSON Lines (.jsonl) formats by checking the file extension.
    """
    if not metadata_path.exists():
        logger.debug(f"[METADATA] {metadata_path.name} does not exist. Returning empty list.")
        return []

    try:
        with metadata_path.open("r") as f:
            if metadata_path.suffix.lower() == ".jsonl":
                # --- JSON Lines (.jsonl) parsing ---
                logger.debug(f"[METADATA] [LOAD] Parsing '{metadata_path.name}' as JSON Lines.")
                entries = []
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
                return entries
            else:
                # --- Standard JSON parsing ---
                logger.debug(f"[METADATA] [LOAD] Parsing '{metadata_path.name}' as standard JSON.")
                content = f.read()
                if not content:
                    logger.warning(
                        f"[METADATA] {metadata_path.name} is empty. Returning empty list."
                    )
                    return []
                return json.loads(content)

    except json.JSONDecodeError:
        logger.error(f"[METADATA] Corrupt JSON in {metadata_path}. Returning empty list.")
        # Archive the corrupt file for debugging
        corrupt_backup_path = Path(
            metadata_path.parent,
            f"{metadata_path.stem}.corrupt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{metadata_path.suffix}",
        )
        try:
            metadata_path.rename(corrupt_backup_path)
            logger.debug(f"[METADATA] Moved corrupt file to {corrupt_backup_path.name}")
        except OSError as e:
            logger.error(f"[METADATA] Failed to move corrupt file {metadata_path.name}: {e}")
        return []
    except OSError as e:
        logger.error(f"[METADATA] Read error {metadata_path}: {e}. Returning empty list.")
        return []
    except Exception as e:
        logger.error(
            f"[METADATA] Unexpecte error reading or parsing file {metadata_path}: {e}",
            exc_info=True,
        )
        return []


def _save_metadata(metadata_path: Path, metadata_list: list):
    temp_metadata_path = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    try:
        with temp_metadata_path.open("w") as f:
            json.dump(metadata_list, f, indent=4)
        temp_metadata_path.replace(metadata_path)
        logger.debug(f"[METADATA] Atomic write successful for {metadata_path.name}")
    except (OSError, TypeError) as e:
        logger.error(f"[METADATA] Save error {metadata_path}: {e}")
        if temp_metadata_path.exists():
            try:
                temp_metadata_path.unlink()
            except OSError:
                pass
        raise  # Re-raise to propagate error


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
        yield  # Passes control back to the 'with' block
    finally:
        _release_lock(lock_fd, file_path.name)
        logger.debug(f"[METADATA] [CONTEXT_LOCK] Released lock for {file_path.name}")


def add_entry(
    manifest_path: Path,
    camera_meta: dict | list[dict] | None,
    temps_meta: dict | None,
):
    """
    Adds one or more new entries to the processing manifest, protected by a file lock.
    Used by Collector.
    """

    try:
        with lock_and_manage_file(manifest_path):
            logger.debug("[METADATA] [ADD] Updating processing manifest (locked section)...")

            metadata_list = _load_metadata(manifest_path)  # Safe to read under lock

            # Normalize camera_meta to always be a list for consistent processing
            cam_entries = []
            if isinstance(camera_meta, list):
                cam_entries = camera_meta
            elif camera_meta is not None:
                cam_entries = [camera_meta]

            if not cam_entries and temps_meta is None:
                logger.warning("[METADATA] [ADD] add_entry called with no data. Nothing to add.")
                return

            # If processing a batch of images, one temp reading applies to all
            if len(cam_entries) > 1 and temps_meta:
                logger.warning(
                    "[METADATA] [ADD] Applying a single temperature reading to a batch of legacy images."
                )

            if not cam_entries and temps_meta:
                cam_entries = [None]

            for cam_entry in cam_entries:
                overall_collection_error = False
                error_messages = []
                if cam_entry and cam_entry.get("error_flag", False):
                    overall_collection_error = True
                    error_messages.append(
                        f"Camera: {cam_entry.get('error_message', 'Unknown error')}"
                    )
                if temps_meta and temps_meta.get("error_flag", False):
                    overall_collection_error = True
                    error_messages.append(
                        f"Temps: {temps_meta.get('error_message', 'Unknown error')}"
                    )

                new_manifest_entry = {
                    "entry_timestamp_iso": datetime.datetime.now().isoformat(),
                    "collection_error": overall_collection_error,
                    "collection_error_msg": " | ".join(error_messages) if error_messages else None,
                    "camera_data": cam_entry,
                    "temperature_data": temps_meta,
                    "processing_status": "pending",  # This field will allow the lock to be released while processing happens
                    "processing_timestamp_iso": None,
                    "processing_error": False,
                    "processing_error_msg": None,
                    "compression_attempted": False,
                    "image_synced": False,
                }
                metadata_list.append(new_manifest_entry)

            _save_metadata(manifest_path, metadata_list)  # Safe to save under lock
            logger.info(f"[METADATA] [ADD] Added {len(cam_entries)} new entries to manifest.")

    except Exception as e:
        logger.error(f"[METADATA] [ADD] Error in add_entry (manifest write): {e}")
        raise  # Re-raise to propagate error to collector


def append_metadata(manifest_path: Path, metadata_to_append: dict | list[dict]):
    """
    Safely appends one or more entries to a metadata file.

    Handles both standard .json (read/write all) and
    .jsonl (append line) formats based on the file extension.
    """
    try:
        with lock_and_manage_file(manifest_path):
            entries_to_add = (
                metadata_to_append
                if isinstance(metadata_to_append, list)
                else [metadata_to_append]
            )
            if not entries_to_add:
                return

            # --- Append Logic ---
            if manifest_path.suffix.lower() == ".jsonl":
                logger.debug(
                    f"Appending {len(entries_to_add)} entries to JSONL file: {manifest_path.name}"
                )
                with manifest_path.open("a") as f:
                    for entry in entries_to_add:
                        json.dump(entry, f)
                        f.write("\n")
            else:
                logger.debug(
                    f"Appending {len(entries_to_add)} entries to JSON file: {manifest_path.name}"
                )
                existing_data = _load_metadata(manifest_path)
                existing_data.extend(entries_to_add)
                _save_metadata(manifest_path, existing_data)

            logger.info(
                f"[METADATA] [APPEND] Successfully appended {len(entries_to_add)} entries to {manifest_path.name}."
            )

    except Exception as e:
        logger.error(f"Error in append_metadata for {manifest_path.name}: {e}", exc_info=True)
        raise


def update_metadata_manifest_entry(
    manifest_path: Path,
    entry_index: int | list[int],
    status: str | list[str] | None = None,
    processing_timestamp_iso: str | list[str] | None = None,
    processing_error: bool | list[bool] | None = None,
    processing_error_msg: str | list[str] | None = None,
    data_transmitted: bool | list[bool] | None = None,
    compression_attempted: bool | list[bool] | None = None,
    image_synced: bool | list[bool] | None = None,
    new_filename: str | list[str] | None = None,
    new_filepath: str | list[str] | None = None,
):
    """
    Updates status and results for one or more entries in the processing manifest.
    If 'entry_index' is a list, data arguments (e.g., 'status', 'processing_error_msg')
    can also be lists of the same length to apply unique values to each entry.
    If data arguments are single values, they are applied to all specified entries.
    """

    try:
        with lock_and_manage_file(manifest_path):
            logger.debug(
                f"[METADATA] [UPDATE] Updating manifest entry {entry_index} status (locked section)..."
            )

            metadata_list = _load_metadata(manifest_path)  # Safe to read under lock

            indices = entry_index if isinstance(entry_index, list) else [entry_index]
            num_indices = len(indices)

            def get_value_for_index(arg, i):
                if isinstance(arg, list):
                    if len(arg) != num_indices:
                        logger.warning(
                            f"[METADATA] [UPDATE] Argument list length mismatch for entry {indices[i]}. Using None."
                        )
                        return None
                    return arg[i]
                return arg

            for i, index_to_update in enumerate(indices):
                if 0 <= index_to_update < len(metadata_list):
                    entry = metadata_list[index_to_update]

                    for key, value in {
                        "processing_status": status,
                        "processing_timestamp_iso": processing_timestamp_iso,
                        "processing_error": processing_error,
                        "processing_error_msg": processing_error_msg,
                        "compression_attempted": compression_attempted,
                        "data_transmitted": data_transmitted,
                        "image_synced": image_synced,
                    }.items():
                        current_value = get_value_for_index(value, i)
                        if current_value is not None:
                            entry[key] = current_value

                    current_filename = get_value_for_index(new_filename, i)
                    if current_filename is not None:
                        if "camera_data" in entry and entry["camera_data"]:
                            entry["camera_data"]["filename"] = current_filename

                    current_filepath = get_value_for_index(new_filepath, i)
                    if current_filepath is not None:
                        if "camera_data" in entry and entry["camera_data"]:
                            entry["camera_data"]["filepath"] = current_filepath
                else:
                    logger.warning(
                        f"[METADATA] [UPDATE] Attempted to update non-existent manifest entry at index {index_to_update}. "
                        f"This can happen if the manifest was backed up and cleared while an item was being processed. "
                        f"The results for this entry will be discarded."
                    )

            _save_metadata(manifest_path, metadata_list)
            logger.info(
                f"[METADATA] [UPDATE] Batch update successful for {len(indices)} manifest entries."
            )

    except Exception as e:
        logger.error(f"[METADATA] [UPDATE] Error in update_manifest_entry_status: {e}")
        raise  # Re-raise to propagate error


def load_metadata_with_lock(metadata_path: Path) -> list:
    """
    Loads metadata from a JSON file using file locking for safety.
    Returns an empty list if the file does not exist or if there's a decoding error.
    """
    try:
        with lock_and_manage_file(metadata_path):
            logger.info("[METADATA] [LOAD] Successfully loaded metadata with lock.")
            return _load_metadata(metadata_path)  # Safe to read under lock
    except Exception as e:
        logger.error(f"[METADATA] [LOAD] Error loading metadata with lock: {e}")
        raise  # Re-raise to propagate error


def save_metadata_with_lock(metadata_path: Path, metadata_list: list):
    """
    Saves results data to a JSON file using file locking and atomic write for safety.
    """
    try:
        with lock_and_manage_file(metadata_path):
            logger.info("[METADATA] [SAVE] Successfully saved metadata with lock.")
            _save_metadata(metadata_path, metadata_list)  # Safe to save under lock
    except Exception as e:
        logger.error(f"[METADATA] [SAVE] Error saving metadata with lock: {e}")
        raise  # Re-raise to propagate error


def move_file_with_lock(source_path: Path, destination_path: Path):
    """
    Safely moves a file using file locks.  This is an atomic operation
    that prevents race conditions with other processes.
    """

    try:
        with lock_and_manage_file(source_path):
            logger.debug(
                f"[METADATA] [MOVE] Moving {source_path.name} to {destination_path.name} (locked section)..."
            )

            if not source_path.exists():
                logger.error(
                    f"[METADATA] [MOVE] Cannot back up {source_path.name} as it does not exist. Skipping."
                )
                return

            destination_path.parent.mkdir(
                parents=True, exist_ok=True
            )  # Ensure destination directory exists

            shutil.move(str(source_path), str(destination_path))
            logger.info(
                f"[METADATA] [MOVE] Successfully moved {source_path.name} to {destination_path.name}."
            )

            # Clean up any associated .tmp files
            temp_file_path = source_path.with_suffix(source_path.suffix + ".tmp")
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                    logger.debug(
                        f"[METADATA] [MOVE] Removed temporary file {temp_file_path.name} after move."
                    )
                except OSError as e:
                    logger.error(
                        f"[METADATA] [MOVE] Failed to remove temporary file {temp_file_path.name}: {e}"
                    )

    except Exception as e:
        logger.error(
            f"[METADATA] [MOVE] An unexpect error occured while moving {source_path.name}: {e}"
        )
        raise


def initialise_status_file(services: list[str]):
    """
    Creates or updates the pipeline_status.json file.
    This non-destructive function will add any new services it is aware of
    without overwriting the status of existing ones.
    """
    status_path = Path(FLAG_DIR, STATUS_FILENAME)
    try:
        with lock_and_manage_file(status_path):
            # 1. Read existing data if the file exists and is not empty
            if status_path.exists() and status_path.stat().st_size > 0:
                with status_path.open("r") as f:
                    current_status = json.load(f)
            else:
                current_status = {}

            # 2. Check for new services and add them if they don't exist
            updated = False
            for service in services:
                if service not in current_status:
                    current_status[service] = {
                        "status": "stopped",
                        "pid": None,
                        "last_heartbeat": None
                    }
                    updated = True
                    logger.info(f"Added new service '{service}' to status file.")

            # 3. Write back to the file only if changes were made or if it's a new file
            if updated or not status_path.exists():
                with status_path.open("w") as f:
                    json.dump(current_status, f, indent=4)
                logger.info(f"Status file at {status_path} is up to date.")
            else:
                logger.info("Status file already contains all services. No changes made.")

    except Exception as e:
        logger.error(f"Failed to initialise status file: {e}", exc_info=True)


def get_pipeline_status() -> dict:
    """
    Safely loads and returns the entire contents of the pipeline_status.json file.
    """
    status_path = Path(FLAG_DIR, STATUS_FILENAME)
    try:
        with lock_and_manage_file(status_path):
            if status_path.exists() and status_path.stat().st_size > 0:
                with status_path.open("r") as f:
                    return json.load(f)
            else:
                return {}
        logger.info(f"[METADATA] [STATUS] Successfully retrieved status file at {status_path}")
    except Exception as e:
        logger.error(f"Failed to get pipeline status: {e}", exc_info=True)
        return {}


def update_service_status(service_name: str, pid: int | None = None, status: str | None = None, heartbeat: bool = False):
    """
    Updates the status, PID, and/or heartbeat timestamp for a given service
    in the pipeline_status.json file.
    """
    status_path = Path(FLAG_DIR, STATUS_FILENAME)
    try:
            current_status = get_pipeline_status()

            # Ensure the service key exists
            if service_name not in current_status:
                current_status[service_name] = {}

            # Update the fields that were provided
            if pid is not None:
                current_status[service_name]['pid'] = pid
            if status is not None:
                current_status[service_name]['status'] = status
            if heartbeat:
                current_status[service_name]['last_heartbeat'] = datetime.datetime.now().isoformat()

            with status_path.open("w") as f:
                json.dump(current_status, f, indent=4)
            logger.info(f"[METADATA] [STATUS] Successfully updated status file at {status_path}")
    except Exception as e:
        logger.error(f"Failed to update status for {service_name}: {e}")
