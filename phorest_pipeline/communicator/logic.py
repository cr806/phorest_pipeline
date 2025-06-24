# src/process_pipeline/communicator/logic.py
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from phorest_pipeline.shared.config import (
    COMMUNICATOR_INTERVAL,
    ENABLE_CAMERA,
    ENABLE_THERMOCOUPLE,
    RESULTS_DIR,
    RESULTS_READY_FLAG,
    settings,
)
from phorest_pipeline.shared.helper_utils import move_existing_files_to_backup
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import load_metadata, save_metadata
from phorest_pipeline.shared.states import CommunicatorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="comms.log")

RESULTS_FILENAME = Path("processing_results.json")
CSV_FILENAME = Path("communicating_results.csv")
RESULTS_IMAGE = Path("processed_data_plot.png")

POLL_INTERVAL = COMMUNICATOR_INTERVAL / 20 if COMMUNICATOR_INTERVAL > (5 * 20) else 5


# Helper Function: Find all processed entries
def find_processed_entries(metadata_list: list) -> list[dict]:
    """Finds all entry indexes with 'processed': True."""
    processed_entries = []
    for entry in metadata_list:
        # Find entry marked as processed
        if entry.get("processing_successful", False):
            processed_entries.append(entry)
    if processed_entries:
        return processed_entries
    return None


def find_not_transmitted_entries(metadata_list: list) -> list[int]:
    """Finds all entry indexes with 'processed': True."""
    processed_entries = []
    for index, entry in enumerate(metadata_list):
        # Find entry marked as processed and not yet transmitted
        if entry.get("processing_successful", False) and not entry.get("data_transmitted", False):
            processed_entries.append(index)
    return processed_entries


def save_results_json_as_csv(processed_entries: list[dict], csv_path: Path) -> None:
    logger.info(f"Parsing results JSON to CSV and saving to {csv_path}")
    
    headers = []
    records = []
    for entry in processed_entries:
        # Extract the image_timestamp once per entry
        timestamp = entry.get("image_timestamp")

        if ENABLE_THERMOCOUPLE:
            # Extract the temperature sensor data once per entry
            temp_sensors = entry.get("temperature_readings", {}).keys()
            temp_dict = {}
            for sensor in temp_sensors:
                temp_dict[f"temperature_{sensor.lower().replace(' ', '_')}"] = entry.get(
                    "temperature_readings", {}
                ).get(sensor, None)

        if ENABLE_CAMERA:
            if not headers:
                try:
                    if len(entry["image_analysis"]) < 2:
                        logger.warning("Expected at least two items in 'image_analysis'. Using first item.")
                        continue
                    target_dictionary = entry["image_analysis"][1]
                    headers = list(target_dictionary.keys())
                except (IndexError, KeyError) as e:
                    logger.error(f"Error accessing data: {e}: {processed_entries = } {target_dictionary = }")
            # Iterate through each item in the "image_analysis" list
            for analysis_item in entry.get("image_analysis", []):
                # We are interested in elements that have "ROI-label" as a key
                if "ROI-label" in analysis_item:
                    image_dict = {}

                    image_dict["timestamp"] = timestamp

                    for field in headers:
                        value = analysis_item.get(field)
                        if isinstance(value, dict):
                            # It's a dictionary so pull out "Mean"
                            value = value.get("Mean")
                        image_dict[field] = value

                    if ENABLE_THERMOCOUPLE:
                        image_dict.update(temp_dict)

                    records.append(image_dict)
        else:
            if ENABLE_THERMOCOUPLE:
                records.append(temp_dict)

    # Create the DataFrame
    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)


def save_plot_of_results(csv_path: Path, image_path: Path) -> None:
    logger.info(f"Generating chart of results and saving to {image_path}")

    # Load the CSV data for plotting
    data = pd.read_csv(csv_path)

    _, ax = plt.subplots(2, 1, figsize=(12, 6))
    if ENABLE_CAMERA:
        analysis_method = data["Analysis-method"].unique()[0]
        value_to_plot = {
            "max_intensity": "max_intensity",
            "centre": "centre",
            "gaussian": "mu",
            "fano": "resonance",
        }

        ROIs_to_plot = data["ROI-label"].unique()
        if len(ROIs_to_plot) == 0:
            logger.warning("No ROI-labels found in the data.")
            return
        for ROI in ROIs_to_plot:
            temp_df = data[data["ROI-label"] == ROI]
            if temp_df.empty:
                logger.warning(f"No data found for ROI-label: {ROI}")
                continue
            ax[0].plot(
                list(range(temp_df["timestamp"].size)),
                temp_df[value_to_plot[analysis_method]],
                label=ROI,
            )
    
    if ENABLE_THERMOCOUPLE:
        temp_sensors_to_plot = [t for t in data.columns if "temperature" in t]
        for temp_sensor in temp_sensors_to_plot:
            ax[1].plot(
                list(range(temp_df["timestamp"].size)), temp_df[temp_sensor], label=temp_sensor
            )

    # ax[0].set_xlabel("Timestep")
    ax[0].set_ylabel("Mean pixel value")
    ax[1].set_ylabel("Temperature (°C)")
    ax[1].set_xlabel("Timestep")
    # ax[1].set_ylim(0, 150)
    ax[0].legend(loc="upper left")
    # plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=60))
    # plt.xticks(rotation=45, ha="right")
    # plt.tight_layout()
    plt.savefig(image_path)


def communicate_results(processed_entries: list[dict], results_data: list[dict]) -> None:
    """Simulate communication of results to a CSV file."""

    csv_path = Path(RESULTS_DIR, CSV_FILENAME)
    save_results_json_as_csv(processed_entries, csv_path)

    image_path = Path(RESULTS_DIR, RESULTS_IMAGE)
    save_plot_of_results(csv_path, image_path)

    # Update the metadata to mark entries as transmitted
    for idx in find_not_transmitted_entries(processed_entries):
        results_data[idx]["data_transmitted"] = True
    # Save the entire updated manifest
    save_metadata(RESULTS_DIR, RESULTS_FILENAME, results_data)


def perform_communication(current_state: CommunicatorState) -> CommunicatorState:
    """State machine logic for the communicator."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return current_state  # Consider a FATAL_ERROR state

    match current_state:
        case CommunicatorState.IDLE:
            logger.info("IDLE -> WAITING_FOR_RESULTS")
            next_state = CommunicatorState.WAITING_FOR_RESULTS
            global next_run_time
            next_run_time = time.monotonic() + COMMUNICATOR_INTERVAL
            logger.info(f"Will now wait for {COMMUNICATOR_INTERVAL} seconds until next cycle...")

        case CommunicatorState.WAITING_FOR_RESULTS:
            now = time.monotonic()
            if now >= next_run_time:
                if RESULTS_READY_FLAG.exists():
                    logger.info(f"Found flag {RESULTS_READY_FLAG}.")
                    # Consume the flag
                    try:
                        RESULTS_READY_FLAG.unlink()
                        logger.info(f"Deleted flag {RESULTS_READY_FLAG}.")
                        logger.info("WAITING_FOR_RESULTS -> COMMUNICATING")
                        next_state = CommunicatorState.COMMUNICATING
                    except FileNotFoundError:
                        logger.info("Flag disappeared before deletion. Re-checking...")
                    except OSError as e:
                        logger.error(f"Could not delete flag {RESULTS_READY_FLAG}: {e}")
                        time.sleep(POLL_INTERVAL)
                else:
                    next_state = CommunicatorState.IDLE
                    logger.info("WAITING_FOR_RESULTS -> IDLE")
            else:
                time.sleep(POLL_INTERVAL)

        case CommunicatorState.COMMUNICATING:
            logger.info("--- Running Communication ---")

            results_data = load_metadata(RESULTS_DIR, RESULTS_FILENAME)
            processed_entries = find_processed_entries(results_data)
            logger.info(f"Found {len(processed_entries)} processed entries to communicate.")
            if processed_entries:
                communicate_results(processed_entries, results_data)

            logger.info("COMMUNICATING -> IDLE")
            next_state = CommunicatorState.IDLE

    return next_state


def run_communicator():
    """Main loop for the communicator process."""
    logger.info("--- Starting Communicator ---")
    print("--- Starting Communicator ---")
    current_state = CommunicatorState.COMMUNICATING
    global next_run_time
    next_run_time = 0

    # Initial cleanup: remove results flag if it exists on startup
    if settings:
        files_to_move = [Path(RESULTS_DIR, CSV_FILENAME), Path(RESULTS_DIR, RESULTS_IMAGE)]
        move_existing_files_to_backup(files_to_move, logger=logger)
        logger.info("Moved existing files to backup directory.")
        try:
            RESULTS_READY_FLAG.unlink(missing_ok=True)
            logger.info(f"Ensured flag {RESULTS_READY_FLAG} is initially removed.")
        except OSError as e:
            logger.warning(f"Could not remove initial flag {RESULTS_READY_FLAG}: {e}")

    try:
        while True:
            current_state = perform_communication(current_state)
            time.sleep(0.1)  # Small sleep to prevent busy-looping
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Cleanup on exit
        if settings:
            logger.info("Cleaning up flags...")
        try:
            RESULTS_READY_FLAG.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"Could not clean up flag {RESULTS_READY_FLAG} on exit: {e}")
        logger.info("--- Communicator Stopped ---")
        print("--- Communicator Stopped ---")
