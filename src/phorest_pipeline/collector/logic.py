# src/process_pipeline/collector/logic.py
import datetime
import time

from phorest_pipeline.shared.config import (
    COLLECTOR_INTERVAL,
    DATA_READY_FLAG,
    POLL_INTERVAL,
    settings,  # Import settings to check if config loaded ok
)
from phorest_pipeline.shared.states import CollectorState


def perform_collection(current_state: CollectorState) -> CollectorState:
    """State machine logic for the collector."""
    next_state = current_state

    if settings is None:
        print('[COLLECTOR] Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)  # Sleep longer on error
        return current_state  # Stay in current (likely IDLE) state

    match current_state:
        case CollectorState.IDLE:
            print('[COLLECTOR] IDLE -> WAITING_TO_RUN')
            next_state = CollectorState.WAITING_TO_RUN
            # Store the next run time
            global next_run_time
            next_run_time = time.monotonic() + COLLECTOR_INTERVAL

        case CollectorState.WAITING_TO_RUN:
            now = time.monotonic()
            if now >= next_run_time:
                print('[COLLECTOR] WAITING_TO_RUN -> COLLECTING')
                next_state = CollectorState.COLLECTING
            else:
                # Print remaining time occasionally
                remaining = next_run_time - now
                # Print frequently near end or every 10s
                if remaining < 5 or int(remaining) % 10 == 0:
                    print(f'[COLLECTOR] Waiting for next run in {remaining:.1f} seconds...')
                time.sleep(POLL_INTERVAL)  # Check periodically

        case CollectorState.COLLECTING:
            print(f'Collector ({datetime.datetime.now().isoformat()}): --- Running Collection ---')
            # Simulate collecting data
            time.sleep(1)
            print('[COLLECTOR] Data collected (simulated).')

            # Set the flag for the processor
            print(f'[COLLECTOR] Creating flag: {DATA_READY_FLAG}')
            try:
                DATA_READY_FLAG.touch()  # Create the empty flag file
                print('[COLLECTOR] --- Collection Done ---')
                print('[COLLECTOR] COLLECTING -> IDLE')
                next_state = CollectorState.IDLE
            except OSError as e:
                print(f'[COLLECTOR] ERROR - Could not create flag {DATA_READY_FLAG}: {e}')
                # Decide how to handle: retry? Log? Halt? For now, just wait.
                time.sleep(POLL_INTERVAL)
                next_state = CollectorState.COLLECTING  # Retry next time

    return next_state


def run_collector():
    """Main loop for the collector process."""
    print('--- Starting Collector ---')
    current_state = CollectorState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0

    # Initial cleanup: remove data ready flag if it exists on startup
    if settings:
        try:
            DATA_READY_FLAG.unlink(missing_ok=True)
            print(f'[COLLECTOR] Ensured flag {DATA_READY_FLAG} is initially removed.')
        except OSError as e:
            print(f'[COLLECTOR] WARNING - Could not remove initial flag {DATA_READY_FLAG}: {e}')

    try:
        while True:
            current_state = perform_collection(current_state)
            # Small sleep even in fast transitions to prevent busy-looping if logic is instant
            if current_state != CollectorState.WAITING_TO_RUN:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print('\n[COLLECTOR] Shutdown requested.')
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
