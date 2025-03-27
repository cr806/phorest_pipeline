# src/process_pipeline/processor/logic.py
import datetime
import time

from phorest_pipeline.shared.config import (
    DATA_READY_FLAG,
    POLL_INTERVAL,
    RESULTS_READY_FLAG,
    settings,
)
from phorest_pipeline.shared.states import ProcessorState


def perform_processing(current_state: ProcessorState) -> ProcessorState:
    """State machine logic for the processor."""
    next_state = current_state

    if settings is None:
        print('[PROCESSOR] Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)
        return current_state

    match current_state:
        case ProcessorState.IDLE:
            print('[PROCESSOR] IDLE -> WAITING_FOR_DATA')
            next_state = ProcessorState.WAITING_FOR_DATA

        case ProcessorState.WAITING_FOR_DATA:
            if DATA_READY_FLAG.exists():
                print(f'[PROCESSOR] Found flag {DATA_READY_FLAG}.')
                # Consume the flag
                try:
                    DATA_READY_FLAG.unlink()
                    print(f'[PROCESSOR] Deleted flag {DATA_READY_FLAG}.')
                    print('[PROCESSOR] WAITING_FOR_DATA -> PROCESSING')
                    next_state = ProcessorState.PROCESSING
                except FileNotFoundError:
                    # Flag disappeared between check and delete (unlikely but possible)
                    print('[PROCESSOR] Flag disappeared before deletion. Re-checking...')
                    next_state = ProcessorState.WAITING_FOR_DATA  # Go back and check again
                except OSError as e:
                    print(f'[PROCESSOR] ERROR - Could not delete flag {DATA_READY_FLAG}: {e}')
                    # Stay in waiting state and retry next time
                    time.sleep(POLL_INTERVAL)
                    next_state = ProcessorState.WAITING_FOR_DATA
            else:
                print('[PROCESSOR] Waiting for data flag...')
                time.sleep(POLL_INTERVAL)
                next_state = ProcessorState.WAITING_FOR_DATA

        case ProcessorState.PROCESSING:
            print(f'Processor ({datetime.datetime.now().isoformat()}): --- Running Processing ---')
            # Simulate processing data
            time.sleep(5)  # Simulate work
            print('[PROCESSOR] Data processed (simulated).')

            # Set the flag for the communicator
            print(f'[PROCESSOR] Creating flag: {RESULTS_READY_FLAG}')
            try:
                RESULTS_READY_FLAG.touch()
                print('[PROCESSOR] --- Processing Done ---')
                print('[PROCESSOR] PROCESSING -> IDLE')
                next_state = ProcessorState.IDLE
            except OSError as e:
                print(f'[PROCESSOR] ERROR - Could not create flag {RESULTS_READY_FLAG}: {e}')
                time.sleep(POLL_INTERVAL)
                next_state = ProcessorState.PROCESSING  # Retry next time

    return next_state


def run_processor():
    """Main loop for the processor process."""
    print('--- Starting Processor ---')
    current_state = ProcessorState.IDLE

    # Initial cleanup: remove flags if they exist on startup
    if settings:
        try:
            DATA_READY_FLAG.unlink(missing_ok=True)
            RESULTS_READY_FLAG.unlink(missing_ok=True)
            print(
                f'[PROCESSOR] Ensured flags {DATA_READY_FLAG}, {RESULTS_READY_FLAG} are initially removed.'
            )
        except OSError as e:
            print(f'[PROCESSOR] WARNING - Could not remove initial flags: {e}')

    try:
        while True:
            current_state = perform_processing(current_state)
            time.sleep(0.1)  # Small sleep to prevent busy-looping
    except KeyboardInterrupt:
        print('\n[PROCESSOR] Shutdown requested.')
    finally:
        # Cleanup on exit
        if settings:
            print('[PROCESSOR] Cleaning up flags...')
        try:
            # Try removing both flags, as the process might be stopped mid-operation
            DATA_READY_FLAG.unlink(missing_ok=True)
            RESULTS_READY_FLAG.unlink(missing_ok=True)
        except OSError as e:
            print(f'[PROCESSOR] ERROR - Could not clean up flags on exit: {e}')
        print('--- Processor Stopped ---')
