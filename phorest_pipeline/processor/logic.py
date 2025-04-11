# phorest_pipeline/processor/logic.py
import datetime
import time
from pathlib import Path

import cv2
import numpy as np

from phorest_pipeline.shared.config import (
    DATA_DIR,
    DATA_READY_FLAG,
    POLL_INTERVAL,
    RESULTS_DIR,
    RESULTS_READY_FLAG,
    settings,  # Check if config loaded
)

# Assuming metadata_manager handles loading/saving the manifest
from phorest_pipeline.shared.metadata_manager import append_metadata, load_metadata, save_metadata
from phorest_pipeline.shared.states import ProcessorState

METADATA_FILENAME = Path('processing_manifest.json')
RESULTS_FILENAME = Path('processing_results.json')


# Helper Function: Find next unprocessed entry
def find_unprocessed_entry(metadata_list: list) -> tuple[int, dict | None]:
    """Finds the index and data of the first entry with 'processed': False."""
    for index, entry in enumerate(metadata_list):
        if not entry.get('processed', False):  # Find first entry not marked as processed
            # Basic validation: Check if necessary data exists in entry
            if entry.get('camera_data') and entry['camera_data'].get('filename'):
                return index, entry
            elif entry.get('temperature_data'):
                # We need the image.
                print(
                    f'[PROCESSOR] [WARN] Entry {index} found unprocessed but missing camera data filename. Skipping.'
                )
            else:
                print(
                    f'[PROCESSOR] [WARN] Entry {index} found unprocessed but missing key data. Skipping.'
                )
    return -1, None


# Helper Function: Process Image
def process_image(image_meta: dict | None) -> tuple[dict | None, str | None]:
    """Loads image and calculates basic statistics."""
    if not image_meta or not image_meta.get('filename') or not image_meta.get('filepath'):
        return None, 'Missing image metadata or filename.'  # No image to process

    image_filename = image_meta['filename']
    data_filepath = image_meta['filepath']
    image_filepath = Path(data_filepath, image_filename)
    processing_results = {}

    try:
        if not image_filepath.exists():
            return None, f'Image file not found: {image_filepath}'

        # Load image in grayscale for analysis
        image = cv2.imread(str(image_filepath), cv2.IMREAD_GRAYSCALE)

        if image is None:
            return None, f'Failed to load image file (may be corrupt): {image_filepath}'

        # 1. Size
        height, width = image.shape
        processing_results['height'] = height
        processing_results['width'] = width

        # 2. Min/Max Pixel Value and Location
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(image)
        processing_results['min_pixel_value'] = float(min_val)
        processing_results['max_pixel_value'] = float(max_val)
        processing_results['min_pixel_loc_xy'] = list(min_loc)  # (x, y) tuple -> list
        processing_results['max_pixel_loc_xy'] = list(max_loc)  # (x, y) tuple -> list

        # 3. Mean and Standard Deviation
        mean, std_dev = cv2.meanStdDev(image)
        processing_results['mean_pixel_value'] = float(mean.item())  # Extract scalar
        processing_results['stddev_pixel_value'] = float(std_dev.item())  # Extract scalar

        # 4. Median
        processing_results['median_pixel_value'] = float(np.median(image))  # type:ignore

        return processing_results, None

    except Exception as e:
        error_msg = f'Error processing image {image_filepath}: {e}'
        print(f'[PROCESSOR] [ERROR] {error_msg}')
        return None, error_msg


# Main State Machine Logic
def perform_processing(current_state: ProcessorState) -> ProcessorState:
    """State machine logic for the processor."""
    next_state = current_state

    if settings is None:
        print('[PROCESSOR] Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)
        # Consider adding a FATAL_ERROR state for the processor too
        return current_state

    match current_state:
        case ProcessorState.IDLE:
            print('[PROCESSOR] IDLE -> WAITING_FOR_DATA')
            next_state = ProcessorState.WAITING_FOR_DATA

        case ProcessorState.WAITING_FOR_DATA:
            if DATA_READY_FLAG.exists():
                print(f'[PROCESSOR] Found flag {DATA_READY_FLAG}. Consuming.')
                try:
                    DATA_READY_FLAG.unlink()
                    print(f'[PROCESSOR] Deleted flag {DATA_READY_FLAG}.')
                    print('[PROCESSOR] WAITING_FOR_DATA -> PROCESSING')
                    next_state = ProcessorState.PROCESSING
                except (FileNotFoundError, OSError) as e:
                    print(f'[PROCESSOR] ERROR - Could not delete flag {DATA_READY_FLAG}: {e}')
                    # Stay waiting, maybe the flag is gone or perms issue
                    time.sleep(POLL_INTERVAL)
                    next_state = ProcessorState.WAITING_FOR_DATA
            else:
                time.sleep(POLL_INTERVAL)
                next_state = ProcessorState.WAITING_FOR_DATA

        case ProcessorState.PROCESSING:
            print(
                f'[PROCESSOR] ({datetime.datetime.now().isoformat()}) --- Checking for Unprocessed Data ---'
            )
            manifest_data = load_metadata(DATA_DIR, METADATA_FILENAME)
            entry_index, entry_to_process = find_unprocessed_entry(manifest_data)

            if entry_to_process:
                print(
                    f'[PROCESSOR] Found unprocessed entry at index {entry_index} (Image: {entry_to_process.get("camera_data", {}).get("filename")})'
                )

                # --- Attempt Processing ---
                image_meta = entry_to_process.get('camera_data')
                image_results, img_proc_error_msg = process_image(image_meta)

                temps_results = entry_to_process.get('temperature_data', {}).get('data')

                processing_timestamp = datetime.datetime.now().isoformat()
                processing_successful = img_proc_error_msg is None

                # --- Aggregate Results ---
                final_result_entry = {
                    'manifest_entry_timestamp': entry_to_process.get('entry_timestamp_iso'),
                    'image_timestamp': entry_to_process.get('camera_data', {}).get(
                        'timestamp_iso'
                    ),
                    'temperature_timestamp': entry_to_process.get('temperature_data', {}).get(
                        'timestamp_iso'
                    ),
                    'image_filename': image_meta.get('filename') if image_meta else None,
                    'processing_timestamp_iso': processing_timestamp,
                    'processing_successful': processing_successful,
                    'processing_error_message': img_proc_error_msg,
                    'image_analysis': image_results,
                    'temperature_readings': temps_results,
                }
                append_metadata(RESULTS_DIR, RESULTS_FILENAME, final_result_entry)

                # --- Update Manifest ---
                entry_to_process['processed'] = True
                entry_to_process['processing_timestamp_iso'] = processing_timestamp
                entry_to_process['processing_error'] = not processing_successful
                entry_to_process['processing_error_msg'] = img_proc_error_msg
                # Replace the old entry with the updated one in the list
                manifest_data[entry_index] = entry_to_process
                # Save the entire updated manifest
                save_metadata(DATA_DIR, METADATA_FILENAME, manifest_data)

                print(
                    f'[PROCESSOR] Processed entry index {entry_index}. Success: {processing_successful}'
                )
                # --- Stay in PROCESSING state ---
                # Immediately check for the next unprocessed entry without waiting for the flag
                next_state = ProcessorState.PROCESSING
                # Optional small delay to prevent tight loop if errors occur fast
                time.sleep(0.1)

            else:
                # No unprocessed entries found
                print('[PROCESSOR] No more unprocessed entries found in manifest.')
                print(f'[PROCESSOR] Creating flag: {RESULTS_READY_FLAG}')
                try:
                    RESULTS_READY_FLAG.touch()
                    print('[PROCESSOR] PROCESSING -> IDLE')
                    next_state = ProcessorState.IDLE
                except OSError as e:
                    print(f'[PROCESSOR] [ERROR] Could not create flag {RESULTS_READY_FLAG}: {e}')
                    time.sleep(POLL_INTERVAL)
                    next_state = ProcessorState.PROCESSING  # Retry flag creation

    return next_state


# Main execution loop function
def run_processor():
    """Main loop for the processor process."""
    print('--- Starting Processor ---')
    # Start in PROCESSING state to immediately clear any backlog
    current_state = ProcessorState.PROCESSING

    # Initial cleanup: remove data flag if it exists on startup
    if settings:
        try:
            DATA_READY_FLAG.unlink(missing_ok=True)
            print(f'[PROCESSOR] Ensured flag {DATA_READY_FLAG} is initially removed.')
            # We don't create RESULTS_READY_FLAG anymore in this design
        except OSError as e:
            print(f'[PROCESSOR] WARNING - Could not remove initial flag {DATA_READY_FLAG}: {e}')

    try:
        while True:
            current_state = perform_processing(current_state)
            # Sleep only when waiting, processing loop handles its own pacing/delays
            if (
                current_state == ProcessorState.WAITING_FOR_DATA
                or current_state == ProcessorState.IDLE
            ):
                time.sleep(0.1)  # Prevent busy-looping when idle/waiting
    except KeyboardInterrupt:
        print('\n[PROCESSOR] Shutdown requested.')
    finally:
        # No flags need specific cleanup here unless DATA_READY might be left mid-operation
        if settings:
            print('[PROCESSOR] Cleaning up flags...')
            try:
                DATA_READY_FLAG.unlink(missing_ok=True)
            except OSError as e:
                print(
                    f'[PROCESSOR] ERROR - Could not clean up flag {DATA_READY_FLAG} on exit: {e}'
                )
        print('--- Processor Stopped ---')
        # Optional: sys.exit based on state if adding FATAL_ERROR
