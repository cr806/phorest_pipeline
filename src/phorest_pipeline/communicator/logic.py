# src/process_pipeline/communicator/logic.py
import datetime
import time

from phorest_pipeline.shared.config import (
    POLL_INTERVAL,
    RESULTS_READY_FLAG,
    settings,
)
from phorest_pipeline.shared.states import CommunicatorState


def perform_communication(current_state: CommunicatorState) -> CommunicatorState:
    """State machine logic for the communicator."""
    next_state = current_state

    if settings is None:
        print('[COMMS] Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)
        return current_state

    match current_state:
        case CommunicatorState.IDLE:
            print('[COMMS] IDLE -> WAITING_FOR_RESULTS')
            next_state = CommunicatorState.WAITING_FOR_RESULTS

        case CommunicatorState.WAITING_FOR_RESULTS:
            if RESULTS_READY_FLAG.exists():
                print(f'[COMMS] Found flag {RESULTS_READY_FLAG}.')
                # Consume the flag
                try:
                    RESULTS_READY_FLAG.unlink()
                    print(f'[COMMS] Deleted flag {RESULTS_READY_FLAG}.')
                    print('[COMMS] WAITING_FOR_RESULTS -> COMMUNICATING')
                    next_state = CommunicatorState.COMMUNICATING
                except FileNotFoundError:
                    print('[COMMS] Flag disappeared before deletion. Re-checking...')
                    next_state = CommunicatorState.WAITING_FOR_RESULTS
                except OSError as e:
                    print(f'[COMMS] ERROR - Could not delete flag {RESULTS_READY_FLAG}: {e}')
                    time.sleep(POLL_INTERVAL)
                    next_state = CommunicatorState.WAITING_FOR_RESULTS
            else:
                print('[COMMS] Waiting for results flag...')
                time.sleep(POLL_INTERVAL)
                next_state = CommunicatorState.WAITING_FOR_RESULTS

        case CommunicatorState.COMMUNICATING:
            print(
                f'Communicator ({datetime.datetime.now().isoformat()}): --- Running Communication ---'
            )
            # Simulate communicating results
            time.sleep(1)
            print('[COMMS] Results communicated (simulated).')
            print('[COMMS] --- Communication Done ---')
            print('[COMMS] COMMUNICATING -> IDLE')
            next_state = CommunicatorState.IDLE

    return next_state


def run_communicator():
    """Main loop for the communicator process."""
    print('--- Starting Communicator ---')
    current_state = CommunicatorState.IDLE

    # Initial cleanup: remove results flag if it exists on startup
    if settings:
        try:
            RESULTS_READY_FLAG.unlink(missing_ok=True)
            print(f'[COMMS] Ensured flag {RESULTS_READY_FLAG} is initially removed.')
        except OSError as e:
            print(
                f'[COMMS] WARNING - Could not remove initial flag {RESULTS_READY_FLAG}: {e}'
            )

    try:
        while True:
            current_state = perform_communication(current_state)
            time.sleep(0.1)  # Small sleep to prevent busy-looping
    except KeyboardInterrupt:
        print('\n[COMMS] Shutdown requested.')
    finally:
        # Cleanup on exit
        if settings:
            print('[COMMS] Cleaning up flags...')
        try:
            RESULTS_READY_FLAG.unlink(missing_ok=True)
        except OSError as e:
            print(
                f'[COMMS] ERROR - Could not clean up flag {RESULTS_READY_FLAG} on exit: {e}'
            )
        print('--- Communicator Stopped ---')
