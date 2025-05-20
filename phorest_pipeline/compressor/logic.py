# phorest_pipeline/compressor/logic.py
import datetime
import time
import shutil
from pathlib import Path
import gzip

import cv2

from phorest_pipeline.shared.config import (
    COMPRESSOR_INTERVAL,
    LOGS_COMPRESSOR_INTERVAL,
    DATA_DIR,
    LOGS_DIR,
    ENABLE_COMPRESSOR,
    settings,
)
from phorest_pipeline.shared.metadata_manager import (
    load_metadata,
    save_metadata,
)
from phorest_pipeline.shared.states import CompressorState
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='compressor.log')

METADATA_FILENAME = Path('processing_manifest.json')
POLL_INTERVAL = 2

def compress_log_files():
    logger.info('--- Compressing Log Files ---')
    output_dir = Path(LOGS_DIR, 'compressed')
    output_dir.mkdir(parents=True, exist_ok=True)

    log_files = list(Path(LOGS_DIR).glob('*.log'))
    if not log_files:
        logger.info('No log files to compress.')
        return
    logger.info(f'Found {len(log_files)} log files to compress.')

    for log_file in log_files:
        try:
            # Create a temporary copy to avoid interrupting ongoing writes
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_log_file = Path(f'{log_file}.temp_{timestamp}')
            shutil.copy2(log_file, temp_log_file)

            output_file = Path(output_dir, f'{log_file.name}.{timestamp}.gz')
            logger.info(f'Compressing {log_file} to {output_file}...')
            with temp_log_file.open('rb') as f_in, gzip.open(output_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

            temp_log_file.unlink(missing_ok=True)
            logger.info(f'Successfully compressed: {log_file} to {output_file}')
        except Exception as e:
            logger.info(f'[ERROR] Error compressing {log_file}: {e}')

def find_entry_to_compress(metadata_list: list) -> tuple[int, dict | None]:
    '''
    Finds index/data of first entry that meets criteria:
    - processed is True
    - compression_attempted is False
    - has camera_data with a .png filename
    '''
    for index, entry in enumerate(metadata_list):
        camera_data = entry.get('camera_data')
        # Check criteria: processed, has camera data, type is 'image', filename is PNG
        if (
            entry.get('processed')
            and not entry.get('compression_attempted', False)
            and camera_data
            and camera_data.get('type') == 'image'  # Check type
            and camera_data.get('filename', '').lower().endswith('.png')
            and Path(camera_data.get('filepath'), camera_data.get('filename')).exists()
        ):
            return index, entry
    return -1, None


def perform_compression_cycle(current_state: CompressorState) -> CompressorState:
    '''State machine logic for the compressor.'''
    next_state = current_state

    if settings is None:
        logger.info('Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)
        return current_state  # Consider a FATAL_ERROR state

    match current_state:
        case CompressorState.IDLE:
            logger.info('IDLE -> CHECKING')
            next_state = CompressorState.CHECKING
            global next_run_time
            next_run_time = time.monotonic() + LOGS_COMPRESSOR_INTERVAL

        case CompressorState.CHECKING:
            logger.info(
                f'({datetime.datetime.now().isoformat()}) --- Checking Manifest for Compression Work ---'
            )
            manifest_data = load_metadata(DATA_DIR, METADATA_FILENAME)
            entry_index, entry_to_compress = find_entry_to_compress(manifest_data)

            if entry_to_compress:
                img_filename = entry_to_compress.get('camera_data', {}).get('filename', 'N/A')
                logger.info(
                    f'Found entry to compress at index {entry_index} (Image: {img_filename})'
                )
                next_state = CompressorState.COMPRESSING_IMAGES
            else:
                logger.info('No entries found requiring compression.')
                next_state = CompressorState.WAITING_TO_RUN

        case CompressorState.COMPRESSING_IMAGES:
            logger.info('--- Starting Compression ---')
            manifest_data = load_metadata(DATA_DIR, METADATA_FILENAME)
            entry_index, entry_to_compress = find_entry_to_compress(manifest_data)

            if not entry_to_compress:
                logger.info('[WARN] Entry to compress disappeared. -> CHECKING')
                next_state = CompressorState.CHECKING
                return next_state

            camera_data = entry_to_compress['camera_data']
            original_filename = Path(camera_data['filename'])
            original_filepath = Path(DATA_DIR, original_filename)

            # Generate new filename and path
            webp_filename = original_filename.with_suffix('.webp')
            webp_filepath = Path(DATA_DIR, webp_filename)

            compression_error_msg = None

            try:
                if not original_filepath.exists():
                    raise FileNotFoundError(f'Original file {original_filepath} not found!')

                logger.info(f'Loading image: {original_filepath}')
                image_gray = cv2.imread(str(original_filepath), cv2.IMREAD_GRAYSCALE)

                if image_gray is None:
                    raise ValueError(
                        f'Failed to load image file (may be corrupt): {original_filepath}'
                    )

                logger.info(f'Compressing to Lossless WebP: {webp_filepath}...')
                # Quality 100 triggers lossless mode for cv2.imwrite with webp
                write_params = [cv2.IMWRITE_WEBP_QUALITY, 100]
                saved = cv2.imwrite(str(webp_filepath), image_gray, write_params)

                if not saved:
                    raise OSError(f'cv2.imwrite failed to save Lossless WebP {webp_filepath}')

                logger.info('Lossless WebP compression successful.')

                # --- Delete Original File ---
                logger.info(f'Deleting original file: {original_filepath}')
                try:
                    original_filepath.unlink()
                    logger.info('Original file deleted.')
                except OSError as del_err:
                    # Log warning but continue, compression itself succeeded
                    logger.warning(
                        f'Failed to delete original file {original_filepath}: {del_err}. Manifest will still be updated.'
                    )

            except Exception as e:
                logger.info(f'[ERROR] Compression failed for {original_filename}: {e}')
                compression_error_msg = f'Compression failed: {e}'

            # --- Update Manifest Entry (update after attempt) ---
            entry_to_compress['compression_attempted'] = True

            # --- Update Manifest Entry ---
            if compression_error_msg is None:
                camera_data['type'] = 'compressed_image'  # Change type
                camera_data['filename'] = webp_filename.as_posix()  # Update filename
            else:  # Compression failed
                camera_data['error_flag'] = True
                existing_error_msg = camera_data.get('error_message', '')
                camera_data['error_message'] = (
                    ' | '.join([existing_error_msg, compression_error_msg])
                    if existing_error_msg
                    else compression_error_msg
                )

            # Save the updated entry back into the list
            manifest_data[entry_index] = entry_to_compress
            save_metadata(DATA_DIR, METADATA_FILENAME, manifest_data)

            status = 'Success' if compression_error_msg is None else 'FAILED'
            logger.info(f'Updated manifest for entry index {entry_index}. Status: {status}')

            # --- Decide Next Step ---
            logger.info('COMPRESSING -> CHECKING (for more work)')
            next_state = CompressorState.CHECKING
            time.sleep(0.1)  # Small pause before checking again

        case CompressorState.WAITING_TO_RUN:
            logger.info(f'Waiting for {COMPRESSOR_INTERVAL} seconds until next check...')
            time.sleep(COMPRESSOR_INTERVAL)
            logger.info('WAITING -> CHECKING')
            now = time.monotonic()
            if now >= next_run_time:
                compress_log_files()
                next_state = CompressorState.IDLE
            else:
                next_state = CompressorState.CHECKING

    return next_state


def run_compressor():
    '''Main loop for the compressor process.'''
    logger.info('--- Starting Compressor ---')
    print('--- Starting Compressor ---')
    if not ENABLE_COMPRESSOR:
        logger.info('Compressor is disabled in config. Exiting.')
        return

    current_state = CompressorState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0
    try:
        while True:
            current_state = perform_compression_cycle(current_state)
            if current_state == CompressorState.IDLE or current_state == CompressorState.CHECKING:
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info('Shutdown requested.')
    finally:
        logger.info('--- Compressor Stopped ---')
        print('--- Compressor Stopped ---')
