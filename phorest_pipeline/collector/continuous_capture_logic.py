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
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.states import CollectorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='continuous_capture.log')

if ENABLE_CAMERA:
    from phorest_pipeline.shared.image_sources import ImageSourceType
    from phorest_pipeline.shared.config import CAMERA_TYPE

    if CAMERA_TYPE == ImageSourceType.LOGITECH:
        from phorest_pipeline.collector.sources.logi_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.ARGUS:
        from phorest_pipeline.collector.sources.argus_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.TIS:
        from phorest_pipeline.collector.sources.tis_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.HAWKEYE:
        from phorest_pipeline.collector.sources.hawkeye_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.DUMMY:
        from phorest_pipeline.collector.sources.dummy_camera_controller import camera_controller
    logger.info(f'Camera type: {CAMERA_TYPE}')

SAVENAME = 'continuous_capture_frame.jpg'
# RESOLUTION = (640, 480)


def perform_continuous_capture(
    current_state: CollectorState, failure_count: int, filename: Path = None
) -> tuple[CollectorState, int]:
    """State machine logic for the continuous capture. Returns (next_state, updated_failure_count)."""
    next_state = current_state
    updated_failure_count = failure_count

    if settings is None:
        logger.error('Configuration error. Halting.')
        return CollectorState.FATAL_ERROR, updated_failure_count  # Exit on config error

    match current_state:
        case CollectorState.IDLE:
            logger.info('IDLE -> COLLECTING')
            next_state = CollectorState.COLLECTING
            updated_failure_count = 0  # Reset failure count when starting new cycle

        case CollectorState.WAITING_TO_RUN:
            logger.info('WAITING_TO_RUN -> COLLECTING')
            next_state = CollectorState.COLLECTING
            updated_failure_count = 0  # Reset failure count when *entering* COLLECTING state

        case CollectorState.COLLECTING:
            logger.info(
                f'Capture ({datetime.datetime.now().isoformat()}): --- Running Continuous Capture ---'
            )
            logger.info(f'Collection Attempt {updated_failure_count + 1}/{FAILURE_LIMIT}')

            collection_successful = True

            if ENABLE_CAMERA:
                logger.info('Camera is enabled.')
                cam_status, cam_msg, _ = camera_controller(CONTINUOUS_DIR, savename=filename)
                if cam_status != 0:
                    collection_successful = False
                    logger.error(cam_msg)
                logger.info(cam_msg)

            if not ENABLE_CAMERA:
                logger.info('No components enabled.')
                next_state = CollectorState.FATAL_ERROR
                return next_state, 0

            if collection_successful:
                logger.info('Data collection successful.')
                updated_failure_count = 0  # Reset failure count on success
                next_state = CollectorState.WAITING_TO_RUN
            else:
                logger.warning('Data collection failed.')
                updated_failure_count += 1  # Increment failure count
                logger.warning(f'Failure count: {updated_failure_count}/{FAILURE_LIMIT}')

                if updated_failure_count >= FAILURE_LIMIT:
                    logger.error(f'Reached failure limit ({FAILURE_LIMIT}).')
                    next_state = CollectorState.FATAL_ERROR
                else:
                    # Stay in COLLECTING state to retry immediately
                    logger.info('Retrying collection...')
                    next_state = CollectorState.COLLECTING
                    logger.info(f'Waiting {RETRY_DELAY}s before retrying...')
                    time.sleep(RETRY_DELAY)

        case CollectorState.FATAL_ERROR:
            # Should not technically be called again once in this state if loop breaks
            logger.error('Shutting down collector.')
            time.sleep(10)  # Sleep long if it somehow gets called

    return next_state, updated_failure_count


def run_continuous_capture():
    """Main loop for the continuous capture process."""
    logger.info('--- Starting Continuous Capture ---')
    current_state = CollectorState.IDLE
    failure_count = 0

    try:
        while True:
            current_state, failure_count = perform_continuous_capture(
                current_state, failure_count, filename=SAVENAME
            )

            # --- Check for FATAL_ERROR state to exit ---
            if current_state == CollectorState.FATAL_ERROR:
                logger.error('Exiting due to FATAL_ERROR state.')
                break  # Exit the while loop

            # Small sleep even in fast transitions to prevent busy-looping if logic is instant
            if current_state == CollectorState.WAITING_TO_RUN:
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info('Shutdown requested via KeyboardInterrupt.')
    except Exception as e:
        logger.error(f'UNEXPECTED ERROR in main loop: {e}')
    finally:
        # Cleanup on exit
        logger.info('--- Collector Stopped ---')
        if current_state == CollectorState.FATAL_ERROR:
            sys.exit(1)
        else:
            sys.exit(0)
