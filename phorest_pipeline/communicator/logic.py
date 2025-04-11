# src/process_pipeline/communicator/logic.py
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

from phorest_pipeline.shared.config import (
    POLL_INTERVAL,
    RESULTS_DIR,
    RESULTS_READY_FLAG,
    settings,
)
from phorest_pipeline.shared.metadata_manager import load_metadata, save_metadata
from phorest_pipeline.shared.states import CommunicatorState

RESULTS_FILENAME = Path('processing_results.json')
CSV_FILENAME = Path('communicating_results.csv')


# Helper Function: Find all processed entries
def find_processed_entries(metadata_list: list) -> list[int]:
    """Finds all entry indexes with 'processed': True."""
    processed_entries = []
    for index, entry in enumerate(metadata_list):
        # Find entry marked as processed and not yet transmitted
        if entry.get('processing_successful', False) and not entry.get('data_transmitted', False):
            processed_entries.append(index)
    return processed_entries


def communicate_results(processed_entries: list[int], results_data: list[dict]) -> None:
    """Simulate communication of results to a CSV file."""
    # If CSV does not exist create it and populate with headers
    csv_path = Path(RESULTS_DIR, CSV_FILENAME)
    if not csv_path.exists():
        with open(csv_path, 'w') as f:
            f.write('timestamp,mean_pixel_value,temperature\n')

    # Append processed data to the CSV file
    with open(csv_path, 'a') as f:
        for idx in processed_entries:
            timestamp = results_data[idx].get('image_timestamp', idx)
            mean_pixel_value = (
                results_data[idx].get('image_analysis', {}).get('mean_pixel_value', None)
            )
            temperature = results_data[idx].get('temperature_readings', {}).get('sensor_1', None)
            f.write(f'{timestamp},{mean_pixel_value},{temperature}\n')

    # Load the CSV data for plotting
    timestamps = []
    pixel_values = []
    with open(csv_path, 'r') as f:
        next(f)
        for line in f:
            if line.strip():
                ts, pv, _ = line.strip().split(',')
                timestamps.append(datetime.fromisoformat(ts))
                pixel_values.append(float(pv))

    # for idx, _ in enumerate(timestamps[1:]):
    #     timestamps[idx] = (timestamps[idx] - timestamps[0]).total_seconds()
    # timestamps[0] = 0

    _, ax = plt.subplots()
    ax.plot(timestamps, pixel_values, color='blue', label='Mean pixel values')
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('Mean pixel value')
    ax.set_title('Mean pixel value')
    plt.savefig(Path(RESULTS_DIR, 'processed_data_plot.png'))

    # Update the metadata to mark entries as transmitted
    for idx in processed_entries:
        results_data[idx]['data_transmitted'] = True
    # Save the entire updated manifest
    save_metadata(RESULTS_DIR, RESULTS_FILENAME, results_data)


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
                f'Communicator ({datetime.now().isoformat()}): --- Running Communication ---'
            )
            # Simulate communicating results
            results_data = load_metadata(RESULTS_DIR, RESULTS_FILENAME)
            processed_entries = find_processed_entries(results_data)

            communicate_results(processed_entries, results_data)

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
            print(f'[COMMS] WARNING - Could not remove initial flag {RESULTS_READY_FLAG}: {e}')

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
            print(f'[COMMS] ERROR - Could not clean up flag {RESULTS_READY_FLAG} on exit: {e}')
        print('--- Communicator Stopped ---')
