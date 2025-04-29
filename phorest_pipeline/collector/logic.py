# process_pipeline/collector/logic.py
import datetime
import sys
import time
from pathlib import Path

from phorest_pipeline.collector.thermocouple_controller import thermocouple_controller
from phorest_pipeline.shared.config import (
    COLLECTOR_INTERVAL,
    DATA_DIR,
    DATA_READY_FLAG,
    ENABLE_CAMERA,
    ENABLE_THERMOCOUPLE,
    FAILURE_LIMIT,
    IMAGE_BUFFER_SIZE,
    RETRY_DELAY,
    settings,  # Import settings to check if config loaded ok
)
from phorest_pipeline.shared.metadata_manager import add_entry
from phorest_pipeline.shared.states import CollectorState

if ENABLE_CAMERA:
    from phorest_pipeline.shared.config import CAMERA_TYPE
    from phorest_pipeline.shared.cameras import CameraType
    if CAMERA_TYPE == CameraType.LOGITECH:
        from phorest_pipeline.collector.logi_camera_controller import camera_controller
    elif CAMERA_TYPE == CameraType.ARGUS:
        from phorest_pipeline.collector.argus_camera_controller import camera_controller
    elif CAMERA_TYPE == CameraType.DUMMY:
        from phorest_pipeline.collector.dummy_camera_controller import camera_controller
    print(f'[COLLECTOR] Camera type: {CAMERA_TYPE}')

METADATA_FILENAME = Path('processing_manifest.json')
POLL_INTERVAL = 2

def ring_buffer_cleanup():
    print('[COLLECTOR] Performing ring buffer cleanup...')
    try:
        # 1. Find relevant image files
        image_files = list(DATA_DIR.glob('*.png'))
        image_files.extend(DATA_DIR.glob('*.webp'))

        # 2. Sort files by modification time (oldest first)
        image_files.sort(key=lambda p: p.stat().st_mtime)

        # 3. Check if buffer limit is exceeded
        num_images = len(image_files)
        print(f'[COLLECTOR] Found {num_images} images. Buffer limit: {IMAGE_BUFFER_SIZE}.')

        if num_images > IMAGE_BUFFER_SIZE:
            num_to_delete = num_images - IMAGE_BUFFER_SIZE
            print(f'[COLLECTOR] Buffer limit exceeded. Deleting {num_to_delete} image(s)...')
            files_to_delete = image_files[:num_to_delete]

            # 4. Delete the oldest files
            for file_to_delete in files_to_delete:
                try:
                    print(f'[COLLECTOR] Deleting: {file_to_delete.name}')
                    file_to_delete.unlink()
                except OSError as delete_err:
                    print(
                        f'[COLLECTOR] [ERROR] Failed to delete image {file_to_delete.name}: {delete_err}'
                    )
        else:
            print('[COLLECTOR] Image count within buffer limit.')

    except Exception as buffer_err:
        # Catch errors during file listing or sorting
        print(f'[COLLECTOR] [ERROR] Error during ring buffer cleanup: {buffer_err}')


def perform_collection(
    current_state: CollectorState, failure_count: int
) -> tuple[CollectorState, int]:
    """State machine logic for the collector. Returns (next_state, updated_failure_count)."""
    next_state = current_state
    updated_failure_count = failure_count

    if settings is None:
        print('[COLLECTOR] Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)
        return CollectorState.FATAL_ERROR, updated_failure_count  # Exit on config error

    match current_state:
        case CollectorState.IDLE:
            print('[COLLECTOR] IDLE -> WAITING_TO_RUN')
            next_state = CollectorState.WAITING_TO_RUN
            updated_failure_count = 0  # Reset failure count when starting new cycle
            global next_run_time
            next_run_time = time.monotonic() + COLLECTOR_INTERVAL

        case CollectorState.WAITING_TO_RUN:
            now = time.monotonic()
            if now >= next_run_time:
                print('[COLLECTOR] WAITING_TO_RUN -> COLLECTING')
                next_state = CollectorState.COLLECTING
                updated_failure_count = 0  # Reset failure count when *entering* COLLECTING state
            else:
                # Print remaining time occasionally
                remaining = next_run_time - now
                if remaining < 5 or int(remaining) % 10 == 0:
                    print(f'[COLLECTOR] Waiting for next run in {remaining:.1f} seconds...')
                time.sleep(POLL_INTERVAL)

        case CollectorState.COLLECTING:
            print(f'Collector ({datetime.datetime.now().isoformat()}): --- Running Collection ---')
            print(f'[COLLECTOR] Collection Attempt {updated_failure_count + 1}/{FAILURE_LIMIT}')

            collection_successful = True

            cam_metadata = None
            if ENABLE_CAMERA:
                print('[COLLECTOR] Camera is enabled.')
                cam_status, cam_msg, cam_metadata = camera_controller(DATA_DIR)
                if cam_status != 0:
                    collection_successful = False
                print(cam_msg)

            tc_metadata = None
            if ENABLE_THERMOCOUPLE:
                print('[COLLECTOR] Thermocouple is enabled.')
                tc_status, tc_msg, tc_metadata = thermocouple_controller(DATA_DIR)
                if tc_status != 0:
                    collection_successful = False
                print(tc_msg)

            if not ENABLE_CAMERA and not ENABLE_THERMOCOUPLE:
                print('[COLLECTOR] No components enabled. Skipping flag creation and buffer.')
                next_state = CollectorState.IDLE
                return next_state, 0

            # Pass the dictionaries directly to the metadata manager
            add_entry(
                data_dir=DATA_DIR,
                metadata_filename=METADATA_FILENAME,
                camera_meta=cam_metadata,
                temps_meta=tc_metadata,
            )

            if collection_successful:
                print('[COLLECTOR] Data collection successful.')
                updated_failure_count = 0  # Reset failure count on success

                ring_buffer_cleanup()

                print(f'[COLLECTOR] Creating flag: {DATA_READY_FLAG}')
                try:
                    DATA_READY_FLAG.touch()
                    print('[COLLECTOR] --- Collection Cycle Done ---')
                    print('[COLLECTOR] COLLECTING -> IDLE')
                    next_state = CollectorState.IDLE
                except OSError as e:
                    print(f'[COLLECTOR] [ERROR] Could not create flag {DATA_READY_FLAG}: {e}')
                    time.sleep(POLL_INTERVAL)
                    next_state = CollectorState.COLLECTING  # Retry flag creation
            else:
                print('[COLLECTOR] Data collection failed.')
                updated_failure_count += 1  # Increment failure count
                print(f'[COLLECTOR] Failure count: {updated_failure_count}/{FAILURE_LIMIT}')

                if updated_failure_count >= FAILURE_LIMIT:
                    print(f'[COLLECTOR] [FATAL ERROR] Reached failure limit ({FAILURE_LIMIT}).')
                    next_state = CollectorState.FATAL_ERROR
                else:
                    # Stay in COLLECTING state to retry immediately
                    print('[COLLECTOR] Retrying collection...')
                    next_state = CollectorState.COLLECTING
                    print(f'[COLLECTOR] Waiting {RETRY_DELAY}s before retrying...')
                    time.sleep(RETRY_DELAY)

        case CollectorState.FATAL_ERROR:
            # Should not technically be called again once in this state if loop breaks
            print('[COLLECTOR] [FATAL ERROR] Shutting down collector.')
            time.sleep(10)  # Sleep long if it somehow gets called

    return next_state, updated_failure_count


def run_collector():
    """Main loop for the collector process."""
    print('--- Starting Collector ---')
    current_state = CollectorState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0
    failure_count = 0

    # Initial cleanup: remove data ready flag if it exists on startup
    if settings:
        try:
            DATA_READY_FLAG.unlink(missing_ok=True)
            print(f'[COLLECTOR] Ensured flag {DATA_READY_FLAG} is initially removed.')
        except OSError as e:
            print(f'[COLLECTOR] WARNING - Could not remove initial flag {DATA_READY_FLAG}: {e}')

    try:
        while True:
            current_state, failure_count = perform_collection(current_state, failure_count)

            # --- Check for FATAL_ERROR state to exit ---
            if current_state == CollectorState.FATAL_ERROR:
                print('[COLLECTOR] Exiting due to FATAL_ERROR state.')
                break  # Exit the while loop

            # Small sleep even in fast transitions to prevent busy-looping if logic is instant
            if current_state != CollectorState.WAITING_TO_RUN:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print('\n[COLLECTOR] Shutdown requested via KeyboardInterrupt.')
    except Exception as e:
        print(f'\n[COLLECTOR] UNEXPECTED ERROR in main loop: {e}')
    finally:
        # Cleanup on exit
        if settings:
            print('[COLLECTOR] Cleaning up flags...')
            try:
                DATA_READY_FLAG.unlink(missing_ok=True)
            except OSError as e:
                print(
                    f'[COLLECTOR] ERROR - Could not clean up flag {DATA_READY_FLAG} on exit: {e}'
                )
        print('--- Collector Stopped ---')
        if current_state == CollectorState.FATAL_ERROR:
            sys.exit(1)
        else:
            sys.exit(0)
