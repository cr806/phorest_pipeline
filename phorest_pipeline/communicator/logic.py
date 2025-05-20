# src/process_pipeline/communicator/logic.py
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from phorest_pipeline.shared.config import (
    RESULTS_DIR,
    RESULTS_READY_FLAG,
    settings,
)
from phorest_pipeline.shared.metadata_manager import load_metadata, save_metadata
from phorest_pipeline.shared.states import CommunicatorState
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='comms.log')

RESULTS_FILENAME = Path('processing_results.json')
CSV_FILENAME = Path('communicating_results.csv')
RESULTS_IMAGE = Path('processed_data_plot.png')
POLL_INTERVAL = 2

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
            f.write('image_timestamp,roi_label,mean_resonance_position,temperature_timestamp,temperature_1,temperature_2\n')

    # Append processed data to the CSV file
    with open(csv_path, 'a') as f:
        for idx in processed_entries:
            image_timestamp = results_data[idx].get('image_timestamp', idx)
            temperature_timestamp = results_data[idx].get('temperature_timestamp', idx)
            image_analysis_list = results_data[idx].get('image_analysis', [])
            mean_pixel_value = (
                image_analysis_list[1].get('mu', None).get('Mean', None)
            )
            roi_label = image_analysis_list[1].get('ROI-label', None)
            temperature_1 = results_data[idx].get('temperature_readings', {}).get('Sensor 1', None)
            temperature_2 = results_data[idx].get('temperature_readings', {}).get('Sensor 2', None)
            f.write(f'{image_timestamp},{roi_label},{mean_pixel_value},{temperature_timestamp},{temperature_1},{temperature_2}\n')

    # Load the CSV data for plotting
    img_timestamps = []
    temp_timestamps = []
    pixel_values = []
    roi_labels = []
    temp_1 = []
    temp_2 = []
    with open(csv_path, 'r') as f:
        next(f)
        for line in f:
            if line.strip():
                i_ts, rl, pv, t_ts, t1, t2 = line.strip().split(',')
                img_timestamps.append(datetime.fromisoformat(i_ts))
                temp_timestamps.append(datetime.fromisoformat(t_ts))
                pixel_values.append(float(pv))
                roi_labels.append(rl)
                temp_1.append(float(t1))
                temp_2.append(float(t2))

    # for idx, _ in enumerate(timestamps[1:]):
    #     timestamps[idx] = (timestamps[idx] - timestamps[0]).total_seconds()
    # timestamps[0] = 0

    _, ax = plt.subplots()
    ax.plot(img_timestamps, pixel_values, color='blue', label=f'{roi_labels[0]}')
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('Mean pixel value')
    ax2 = ax.twinx()
    ax2.plot(temp_timestamps, temp_1, color='red', label='Temperature 1')
    ax2.plot(temp_timestamps, temp_2, color='green', label='Temperature 2')
    ax2.set_ylabel('Temperature (°C)')
    ax2.set_ylim(0, 100)
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')
    plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=30))
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(Path(RESULTS_DIR, RESULTS_IMAGE))

    # Update the metadata to mark entries as transmitted
    for idx in processed_entries:
        results_data[idx]['data_transmitted'] = True
    # Save the entire updated manifest
    save_metadata(RESULTS_DIR, RESULTS_FILENAME, results_data)


def perform_communication(current_state: CommunicatorState) -> CommunicatorState:
    """State machine logic for the communicator."""
    next_state = current_state

    if settings is None:
        logger.info('Configuration error. Halting.')
        time.sleep(POLL_INTERVAL * 5)
        return current_state

    match current_state:
        case CommunicatorState.IDLE:
            logger.info('IDLE -> WAITING_FOR_RESULTS')
            next_state = CommunicatorState.WAITING_FOR_RESULTS

        case CommunicatorState.WAITING_FOR_RESULTS:
            if RESULTS_READY_FLAG.exists():
                logger.info(f'Found flag {RESULTS_READY_FLAG}.')
                # Consume the flag
                try:
                    RESULTS_READY_FLAG.unlink()
                    logger.info(f'Deleted flag {RESULTS_READY_FLAG}.')
                    logger.info('WAITING_FOR_RESULTS -> COMMUNICATING')
                    next_state = CommunicatorState.COMMUNICATING
                except FileNotFoundError:
                    logger.info('Flag disappeared before deletion. Re-checking...')
                    next_state = CommunicatorState.WAITING_FOR_RESULTS
                except OSError as e:
                    logger.error(f'- Could not delete flag {RESULTS_READY_FLAG}: {e}')
                    time.sleep(POLL_INTERVAL)
                    next_state = CommunicatorState.WAITING_FOR_RESULTS
            else:
                logger.info('Waiting for results flag...')
                time.sleep(POLL_INTERVAL)
                next_state = CommunicatorState.WAITING_FOR_RESULTS

        case CommunicatorState.COMMUNICATING:
            logger.info(
                f'Communicator ({datetime.now().isoformat()}): --- Running Communication ---'
            )
            # Simulate communicating results
            results_data = load_metadata(RESULTS_DIR, RESULTS_FILENAME)
            processed_entries = find_processed_entries(results_data)

            communicate_results(processed_entries, results_data)

            logger.info('Results communicated (simulated).')
            logger.info('--- Communication Done ---')
            logger.info('COMMUNICATING -> IDLE')
            next_state = CommunicatorState.IDLE

    return next_state


def run_communicator():
    """Main loop for the communicator process."""
    logger.info('--- Starting Communicator ---')
    print('--- Starting Communicator ---')
    current_state = CommunicatorState.COMMUNICATING

    # Initial cleanup: remove results flag if it exists on startup
    if settings:
        try:
            RESULTS_READY_FLAG.unlink(missing_ok=True)
            logger.info(f'Ensured flag {RESULTS_READY_FLAG} is initially removed.')
        except OSError as e:
            logger.warning(f'Could not remove initial flag {RESULTS_READY_FLAG}: {e}')

    try:
        while True:
            current_state = perform_communication(current_state)
            time.sleep(0.1)  # Small sleep to prevent busy-looping
    except KeyboardInterrupt:
        logger.info('Shutdown requested.')
    finally:
        # Cleanup on exit
        if settings:
            logger.info('Cleaning up flags...')
        try:
            RESULTS_READY_FLAG.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f'Could not clean up flag {RESULTS_READY_FLAG} on exit: {e}')
        logger.info('--- Communicator Stopped ---')
        print('--- Communicator Stopped ---')
