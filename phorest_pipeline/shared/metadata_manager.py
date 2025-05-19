# phorest_pipeline/shared/metadata_manager.py
import datetime
import json
import os
from pathlib import Path
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='shared.log')

def load_metadata(data_dir: Path, metadata_filename: Path) -> list:
    # ... (load_metadata remains the same) ...
    metadata_path = Path(data_dir, metadata_filename)
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                content = f.read()
                if not content:
                    return []
                return json.loads(content)
        except json.JSONDecodeError:
            logger.error(f'[METADATA] Corrupt JSON in {metadata_path}. Returning empty list.')
            # Backup corrupted file: metadata_path.rename(metadata_path.with_suffix(".corrupt"))
            return []
        except OSError as e:
            logger.error(f'[METADATA] Read error {metadata_path}: {e}. Returning empty list.')
            return []
    else:
        return []


def save_metadata(data_dir: Path, metadata_filename: Path, metadata_list: list):
    metadata_path = Path(data_dir, metadata_filename)
    temp_metadata_path = metadata_path.with_suffix(metadata_path.suffix + '.tmp')
    try:
        with open(temp_metadata_path, 'w') as f:
            json.dump(metadata_list, f, indent=4)
        os.replace(temp_metadata_path, metadata_path)
    except (OSError, TypeError) as e:
        logger.error(f'[METADATA] Save error {metadata_path}: {e}')
        if temp_metadata_path.exists():
            try:
                temp_metadata_path.unlink()
            except OSError:
                pass


def add_entry(
    data_dir: Path, metadata_filename: Path, camera_meta: dict | None, temps_meta: dict | None
):
    """Adds a new combined entry based on controller metadata."""
    logger.info('[METADATA] Updating metadata file...')
    metadata_list = load_metadata(data_dir, metadata_filename)

    # Determine overall success based on *if both components ran and succeeded*
    # Note: Controllers now return metadata even on error, use their error_flag
    overall_collection_error = False
    error_messages = []
    if camera_meta and camera_meta.get('error_flag', False):
        overall_collection_error = True
        error_messages.append(f'Camera: {camera_meta.get("error_message", "Unknown error")}')
    if temps_meta and temps_meta.get('error_flag', False):
        overall_collection_error = True
        error_messages.append(f'Temps: {temps_meta.get("error_message", "Unknown error")}')

    # Create the new entry for the manifest
    new_manifest_entry = {
        'entry_timestamp_iso': datetime.datetime.now().isoformat(),
        'collection_error': overall_collection_error,  # Overall status
        'collection_error_msg': ' | '.join(error_messages) if error_messages else None,
        'camera_data': camera_meta,  # Embed the camera dict (or None)
        'temperature_data': temps_meta,  # Embed the temps dict (or None)
        # 'processed': False,  # Initial state for the processor
        # 'processing_timestamp_iso': None,
        # 'processing_error': None,
        # 'processing_error_msg': None,
        # 'compression_attempted': False,
    }

    metadata_list.append(new_manifest_entry)
    save_metadata(data_dir, metadata_filename, metadata_list)
    img_name = camera_meta.get('filename') if camera_meta else 'N/A'
    status = 'FAILED' if overall_collection_error else 'OK'
    logger.info(f'[METADATA] Added entry: Status={status}, Image={img_name}')


def append_metadata(data_dir: Path, metadata_filename: Path, metadata_dict: dict):
    """Appends a new entry to the metadata file."""
    logger.info('[METADATA] Updating metadata file...')
    metadata_list = load_metadata(data_dir, metadata_filename)
    metadata_list.append(metadata_dict)
    save_metadata(data_dir, metadata_filename, metadata_list)
