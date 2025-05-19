# process_pipeline/collector/logic.py
import datetime
import sys
import time

from pathlib import Path

from phorest_pipeline.shared.config import (
    CONTINUOUS_DIR,
    ENABLE_CAMERA,
    FAILURE_LIMIT,
    RETRY_DELAY,
    settings,  # Import settings to check if config loaded ok
)
from phorest_pipeline.shared.states import CollectorState

if ENABLE_CAMERA:
    from phorest_pipeline.shared.cameras import CameraType
    from phorest_pipeline.shared.config import CAMERA_TYPE
    if CAMERA_TYPE == CameraType.LOGITECH:
        from phorest_pipeline.collector.logi_camera_controller import camera_controller
    elif CAMERA_TYPE == CameraType.ARGUS:
        from phorest_pipeline.collector.argus_camera_controller import camera_controller
    elif CAMERA_TYPE == CameraType.TIS:
        from phorest_pipeline.collector.tis_camera_controller import camera_controller
    elif CAMERA_TYPE == CameraType.DUMMY:
        from phorest_pipeline.collector.dummy_camera_controller import camera_controller
    print(f'[CONTINUOUS CAPTURE] Camera type: {CAMERA_TYPE}')

SAVENAME = 'continuous_capture_frame.jpg'

def perform_continuous_capture(
    current_state: CollectorState, failure_count: int, filename: Path = None
) -> tuple[CollectorState, int]:
    """State machine logic for the continuous capture. Returns (next_state, updated_failure_count)."""
    next_state = current_state
    updated_failure_count = failure_count

    if settings is None:
        print('[CONTINUOUS CAPTURE] Configuration error. Halting.')
        return CollectorState.FATAL_ERROR, updated_failure_count  # Exit on config error

    match current_state:
        case CollectorState.IDLE:
            print('[CONTINUOUS CAPTURE] IDLE -> COLLECTING')
            next_state = CollectorState.COLLECTING
            updated_failure_count = 0  # Reset failure count when starting new cycle

        case CollectorState.WAITING_TO_RUN:
            print('[CONTINUOUS CAPTURE] WAITING_TO_RUN -> COLLECTING')
            next_state = CollectorState.COLLECTING
            updated_failure_count = 0  # Reset failure count when *entering* COLLECTING state

        case CollectorState.COLLECTING:
            print(f'Capture ({datetime.datetime.now().isoformat()}): --- Running Continuous Capture ---')
            print(f'[CONTINUOUS CAPTURE] Collection Attempt {updated_failure_count + 1}/{FAILURE_LIMIT}')

            collection_successful = True

            if ENABLE_CAMERA:
                print('[CONTINUOUS CAPTURE] Camera is enabled.')
                cam_status, cam_msg, _ = camera_controller(CONTINUOUS_DIR, savename=filename)
                if cam_status != 0:
                    collection_successful = False
                print(cam_msg)

            if not ENABLE_CAMERA:
                print('[CONTINUOUS CAPTURE] No components enabled.')
                next_state = CollectorState.FATAL_ERROR
                return next_state, 0

            if collection_successful:
                print('[CONTINUOUS CAPTURE] Data collection successful.')
                updated_failure_count = 0  # Reset failure count on success
                next_state = CollectorState.WAITING_TO_RUN
            else:
                print('[CONTINUOUS CAPTURE] Data collection failed.')
                updated_failure_count += 1  # Increment failure count
                print(f'[CONTINUOUS CAPTURE] Failure count: {updated_failure_count}/{FAILURE_LIMIT}')

                if updated_failure_count >= FAILURE_LIMIT:
                    print(f'[CONTINUOUS CAPTURE] [FATAL ERROR] Reached failure limit ({FAILURE_LIMIT}).')
                    next_state = CollectorState.FATAL_ERROR
                else:
                    # Stay in COLLECTING state to retry immediately
                    print('[CONTINUOUS CAPTURE] Retrying collection...')
                    next_state = CollectorState.COLLECTING
                    print(f'[CONTINUOUS CAPTURE] Waiting {RETRY_DELAY}s before retrying...')
                    time.sleep(RETRY_DELAY)

        case CollectorState.FATAL_ERROR:
            # Should not technically be called again once in this state if loop breaks
            print('[CONTINUOUS CAPTURE] [FATAL ERROR] Shutting down collector.')
            time.sleep(10)  # Sleep long if it somehow gets called

    return next_state, updated_failure_count


def run_continuous_capture():
    """Main loop for the continuous capture process."""
    print('--- Starting Continuous Capture ---')
    current_state = CollectorState.IDLE
    failure_count = 0

    try:
        while True:
            current_state, failure_count = perform_continuous_capture(current_state, failure_count, filename=SAVENAME)

            # --- Check for FATAL_ERROR state to exit ---
            if current_state == CollectorState.FATAL_ERROR:
                print('[CONTINUOUS CAPTURE] Exiting due to FATAL_ERROR state.')
                break  # Exit the while loop

            # Small sleep even in fast transitions to prevent busy-looping if logic is instant
            if current_state == CollectorState.WAITING_TO_RUN:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print('\n[CONTINUOUS CAPTURE] Shutdown requested via KeyboardInterrupt.')
    except Exception as e:
        print(f'\n[CONTINUOUS CAPTURE] UNEXPECTED ERROR in main loop: {e}')
    finally:
        # Cleanup on exit
        print('--- Collector Stopped ---')
        if current_state == CollectorState.FATAL_ERROR:
            sys.exit(1)
        else:
            sys.exit(0)
