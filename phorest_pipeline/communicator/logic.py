# src/process_pipeline/communicator/logic.py
import sys
import time
from pathlib import Path

import matplotlib.dates as mdates
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
from phorest_pipeline.shared.metadata_manager import (
    load_metadata_with_lock,
    lock_and_manage_file,
    save_metadata_with_lock,
)
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
    return processed_entries


def find_not_transmitted_entries_indices(metadata_list: list) -> list[int]:
    """Finds all entry indexes with 'processed': True."""
    not_transmitted_indices = []
    for index, entry in enumerate(metadata_list):
        # Find entry marked as processed and not yet transmitted
        if entry.get("processing_successful", False) and not entry.get("data_transmitted", False):
            not_transmitted_indices.append(index)
    return not_transmitted_indices


def save_results_json_as_csv(processed_entries: list[dict], csv_path: Path) -> None:
    logger.info(f"Parsing results JSON to CSV and saving to {csv_path}")

    if not processed_entries:
        logger.info("No processed entries provided for CSV conversion. Skipping.")
        # Ensure an empty CSV is created or old one is cleared if no data
        try:
            pd.DataFrame().to_csv(csv_path, index=False)
            logger.info(f"Created/cleared empty CSV at {csv_path}")
        except Exception as e:
            logger.error(f"Failed to create/clear CSV at {csv_path}: {e}")
        return

    headers = []
    records = []
    for entry in processed_entries:
        # Extract the image_timestamp once per entry
        timestamp = entry.get("image_timestamp", None)

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
                        logger.warning(
                            "Expected at least two items in 'image_analysis'. Using first item."
                        )
                        continue
                    target_dictionary = entry["image_analysis"][1]
                    headers = list(target_dictionary.keys())
                except (IndexError, KeyError) as e:
                    logger.error(
                        f"Error accessing data: {e}: {processed_entries = } {target_dictionary = }"
                    )
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
                if not timestamp:
                    temp_dict["timestamp"] = entry.get("temperature_timestamp", None)
                records.append(temp_dict)

    # Create the DataFrame
    df = pd.DataFrame(records)
    try:
        with lock_and_manage_file(csv_path):
            df.to_csv(csv_path, index=False)
            logger.info(f"Successfully saved CSV to {csv_path} (under lock).")
    except Exception as e:
        logger.error(f"Failed to save CSV file under lock at {csv_path}: {e}", exc_info=True)


def save_plot_of_results(csv_path: Path, image_path: Path) -> None:
    logger.info(f"Generating chart of results and saving to {image_path}")

    if not csv_path.exists() or csv_path.stat().st_size == 0:
        logger.warning(
            f"CSV file for plotting not found or is empty at {csv_path}. Skipping plot generation."
        )
        # Ensure previous plot is cleared or not generated
        if image_path.exists():
            try:
                image_path.unlink()
                logger.info(f"Removed old plot image: {image_path.name}")
            except OSError as e:
                logger.error(f"Failed to remove old plot image {image_path.name}: {e}")
        return

    # Load the CSV data for plotting
    data = pd.read_csv(csv_path)

    if data.empty:
        logger.warning("No data in CSV after loading. Skipping plot generation.")
        if image_path.exists():
            try:
                image_path.unlink()
                logger.info(f"Removed old plot image: {image_path.name}")
            except OSError as e:
                logger.error(f"Failed to remove old plot image {image_path.name}: {e}")
        return

    # Convert timestamp column to datetime objects for plotting
    data["timestamp"] = pd.to_datetime(data["timestamp"])

    fig, ax = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # Format x-axis as time
    formatter = mdates.DateFormatter("%H:%M:%S")
    ax[1].xaxis.set_major_formatter(formatter)
    plt.setp(ax[1].xaxis.get_majorticklabels(), rotation=45, ha="right")  # Rotate for readability

    if ENABLE_CAMERA:
        if "Analysis-method" in data.columns and not data["Analysis-method"].empty:
            analysis_method = data["Analysis-method"].unique()[0]

            value_to_plot = {
                "max_intensity": "max_intensity",
                "centre": "centre",
                "gaussian": "mu",
                "fano": "resonance",
            }

            plot_col_name = value_to_plot.get(analysis_method)
            if plot_col_name and plot_col_name in data.columns:
                ROIs_to_plot = data["ROI-label"].unique()
                if ROIs_to_plot.size == 0:
                    logger.warning("No ROI-labels found in the data.")
                else:
                    for ROI in ROIs_to_plot:
                        temp_df = data[data["ROI-label"] == ROI]
                        if temp_df.empty:
                            logger.warning(f"No data found for ROI-label: {ROI}")
                            continue
                        ax[0].plot(
                            # list(range(temp_df["timestamp"].size)),
                            temp_df["timestamp"],
                            temp_df[plot_col_name],
                            label=ROI,
                        )
            else:
                logger.warning(
                    f"Column to plot '{plot_col_name}' not found for analysis method '{analysis_method}'. Skipping camera plot."
                )
        else:
            logger.warning("No 'Analysis-method' column found in data. Skipping camera plot.")
    else:
        logger.info("Camera not enabled. Skipping image analysis plot.")

    if ENABLE_THERMOCOUPLE:
        temp_sensors_to_plot = [t for t in data.columns if "temperature" in t]
        if temp_sensors_to_plot:
            for temp_sensor in temp_sensors_to_plot:
                if temp_sensor in data.columns:
                    ax[1].plot(
                        # list(range(temp_df["timestamp"].size)),
                        temp_df["timestamp"],
                        temp_df[temp_sensor],
                        label=temp_sensor,
                    )
                else:
                    logger.warning(
                        f"Temperature sensor '{temp_sensor}' not found in data. Skipping plot for this sensor."
                    )
            ax[1].legend(loc="upper left")
        else:
            logger.warning("No temperature sensors found in data. Skipping temperature plot.")
    else:
        logger.info("Thermocouple not enabled. Skipping temperature plot.")

    ax[0].set_ylabel("Mean pixel value")
    ax[1].set_ylabel("Temperature (°C)")
    ax[1].set_xlabel("Time")


    ax[0].legend(loc="upper left", ncols=5)

    fig.tight_layout()
    try:
        with lock_and_manage_file(image_path):
            plt.savefig(image_path, dpi=300)
            logger.info(f"Chart saved to {image_path} (under lock).")
    except Exception as e:
        logger.error(f"Failed to save plot under lock at {image_path}: {e}", exc_info=True)
    finally:
        plt.close(fig)


def communicate_results(processed_entries: list[dict], results_data: list[dict]) -> None:
    """Simulate communication of results to a CSV file."""

    if not processed_entries:
        logger.info("No processed entries to communicate. Skipping CSV/plot generation.")
        return

    csv_path = Path(RESULTS_DIR, CSV_FILENAME)
    image_path = Path(RESULTS_DIR, RESULTS_IMAGE)

    try:
        save_results_json_as_csv(processed_entries, csv_path)
        save_plot_of_results(csv_path, image_path)
    except Exception as e:
        logger.error(f"Error during CSV/Plot generation: {e}", exc_info=True)
        return

    # --- Update the results JSON to mark entries as transmitted ---
    # Need to load the manifest again under lock *just* before modifying and saving
    # to ensure we have the most up-to-date version and don't overwrite changes
    # from the processor that might have occurred between the initial load and now.

    logger.info("Attempting to update processing_results.json to mark entries as transmitted.")
    try:
        indices_to_mark_transmitted = find_not_transmitted_entries_indices(results_data)

        # Load the latest version of the results file under lock
        current_results_data_for_update = load_metadata_with_lock(RESULTS_DIR, RESULTS_FILENAME)

        # Apply updates to the new data
        for idx_in_original_list in indices_to_mark_transmitted:
            if 0 <= idx_in_original_list < len(current_results_data_for_update):
                current_results_data_for_update[idx_in_original_list]["data_transmitted"] = True
            else:
                logger.warning(
                    f"Attempted to mark non-existent entry at index {idx_in_original_list} as transmitted. Data inconsistency?"
                )

        # Save the entire updated manifest back under lock
        save_metadata_with_lock(RESULTS_DIR, RESULTS_FILENAME, current_results_data_for_update)
        logger.info(
            "Successfully marked processed entries as transmitted in processing_results.json."
        )

    except Exception as e:
        logger.error(
            f"CRITICAL ERROR: Failed to update processing_results.json to mark transmitted entries: {e}",
            exc_info=True,
        )
        # TODO: This is a critical failure. The system will retry but these entries won't be marked.
        #       Consider a FATAL_ERROR state for the communicator if this persists.


def perform_communication(current_state: CommunicatorState) -> CommunicatorState:
    """State machine logic for the communicator."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return CommunicatorState.FATAL_ERROR

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
                        next_state = CommunicatorState.WAITING_FOR_RESULTS
                    except OSError as e:
                        logger.error(f"Could not delete flag {RESULTS_READY_FLAG}: {e}")
                        next_state = CommunicatorState.WAITING_FOR_RESULTS
                        time.sleep(POLL_INTERVAL)
                else:
                    next_state = CommunicatorState.IDLE
                    logger.info("WAITING_FOR_RESULTS -> IDLE")
            else:
                time.sleep(POLL_INTERVAL)

        case CommunicatorState.COMMUNICATING:
            logger.info("--- Running Communication ---")

            try:
                results_data = load_metadata_with_lock(RESULTS_DIR, RESULTS_FILENAME)
                processed_entries = find_processed_entries(results_data)
                logger.info(f"Found {len(processed_entries)} processed entries to communicate.")
                if processed_entries:
                    communicate_results(processed_entries, results_data)

                logger.info("COMMUNICATING -> IDLE")
                next_state = CommunicatorState.IDLE
            except Exception as e:
                logger.error(f"Error during COMMUNICATING state: {e}", exc_info=True)
                # If loading fails, or any part of communication, retry after a delay
                next_state = CommunicatorState.COMMUNICATING  # Stay in COMMUNICATING to retry
                time.sleep(POLL_INTERVAL * 5)

        case CommunicatorState.FATAL_ERROR:
            logger.error("[FATAL ERROR] Shutting down communicator.")
            time.sleep(10)  # Prevent busy-looping in fatal state

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
            if current_state == CommunicatorState.FATAL_ERROR:
                logger.error("Exiting due to FATAL_ERROR state.")
                break
            time.sleep(0.1)  # Small sleep to prevent busy-looping
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        current_state = CommunicatorState.FATAL_ERROR
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
        if current_state == CommunicatorState.FATAL_ERROR:
            sys.exit(1)  # Exit with error code if fatal
        else:
            sys.exit(0)  # Exit cleanly
