import datetime
from pathlib import Path

from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='data_source.log')

SUPPORTED_EXT = ['.png', '.jpg', '.jpeg', '.tif', '.tiff']

def image_file_importer(data_dir: Path) -> tuple[int, str, list[dict] | None]:
    """
    Scans a directory for existing images and generates a list of metadata entries.
    This controller runs only once and returns all data as a single batch.
    """
    logger.info('[IMAGE IMPORTER] --- Starting Image File Importer ---')

    all_metadata_entries = []

    try:
        if not data_dir.is_dir():
            return (1, f"Data directory '{data_dir} not found.", None)
        
        logger.info(f"[IMAGE IMPORTER] Scanning '{data_dir}' for image files...")
        image_files = [p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXT]

        if not image_files:
            return(1, "No image files found in the data directory.", None)
        
        image_files.sort(key=lambda p: p.name)
        logger.info(f"Found {len(image_files)} images. Generating manifest entries...")

        for image_path in image_files:
            capture_timestamp = datetime.datetime.fromtimestamp(image_path.stat().st_mtime)
            metadata_dict = {
                'type': 'image',
                'filename': image_path.name,
                'filepath': image_path.parent.resolve().as_posix(),
                'timestamp_iso': capture_timestamp.isoformat(),
                'camera_index': 'IMAGE_IMPORTER',
                'error_flag': False,
                'error_message': None,
            }
            all_metadata_entries.append(metadata_dict)

        msg = f"Successfully generated {len(all_metadata_entries)} manifest entries from legacy data."
        logger.info(msg)
        return (0, msg, all_metadata_entries)
    
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return (1, f"Unexpected error in legacy importer: {e}", None)
