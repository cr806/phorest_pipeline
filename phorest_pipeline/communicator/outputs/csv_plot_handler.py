from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from phorest_pipeline.shared.config import (
    ENABLE_CAMERA,
    ENABLE_THERMOCOUPLE,
    RESULTS_DIR,
    RESULTS_FILENAME,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import load_metadata_with_lock, lock_and_manage_file

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="comms_csv_plot.log")

CSV_FILENAME = Path("communicating_results.csv")
RESULTS_IMAGE = Path("processed_data_plot.png")


def save_results_json_as_csv(processed_entries: list[dict], csv_path: Path) -> None:
    """
    Combines data from the data manifest and the results manifest to create a CSV.
    """
    logger.debug("Loading results manifest to correlate with processed entries...")
    try:
        results_data = load_metadata_with_lock(Path(RESULTS_DIR, RESULTS_FILENAME))

        results_map = {
            entry.get("image_filename"): entry 
            for entry in results_data if entry.get("image_filename")
        }
    except Exception as e:
        logger.error(f"Could not load or parse results manifest: {e}", exc_info=True)
        return
    
    logger.info(f"Parsing {len(processed_entries)} entries to create CSV...")
    records = []

    for entry in processed_entries:
        if not entry.get("camera_data"):
            continue

        filename = entry["camera_data"].get("filename")
        result_entry = results_map.get(filename)

        if not result_entry:
            logger.warning(f"No matching result found for processed image: {filename}. Skipping entry.")
            continue

        timestamp = result_entry.get("image_timestamp")
        temp_readings = result_entry.get("temperature_readings")
        image_analysis = result_entry.get("image_analysis")

        headers = []
        if not headers and ENABLE_CAMERA and image_analysis:
            for item in image_analysis:
                if "ROI-label" in item:
                    headers = list(item.keys())
                    break
        
        if ENABLE_CAMERA and image_analysis:
            for analysis_item in image_analysis:
                if "ROI-label" in analysis_item:
                    record = {"timestamp": timestamp}
                    for field in headers:
                        value = analysis_item.get(field)
                        if isinstance(value, dict):
                            value = value.get("Median")
                        record[field] = value
                    
                    # Add temperature data to the same record
                    if ENABLE_THERMOCOUPLE and temp_readings:
                        for sensor, value in temp_readings.items():
                            record[f"temperature_{sensor.lower().replace(' ', '_')}"] = value
                    
                    records.append(record)

        elif ENABLE_THERMOCOUPLE and temp_readings:
            record = {"timestamp": result_entry.get("temperature_timestamp")}
            for sensor, value in temp_readings.items():
                record[f"temperature_{sensor.lower().replace(' ', '_')}"] = value
            records.append(record)

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
                logger.debug(f"Removed old plot image: {image_path.name}")
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
                logger.debug(f"Removed old plot image: {image_path.name}")
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
            ax[1].legend(loc="upper left", ncols=5)
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


def generate_report(processed_entries: list[dict]) -> bool:
    """
    Main entru point for CSV/Plot handler.  Generates the CSV and plot from the
    given data.  Returns True on success, False on failure
    """
    if not processed_entries:
        logger.info("No processed entries to generate report...")
        return True
    
    csv_path = Path(RESULTS_DIR, CSV_FILENAME)
    image_path = Path(RESULTS_DIR, RESULTS_IMAGE)

    try:
        save_results_json_as_csv (processed_entries, csv_path)
        save_plot_of_results(csv_path, image_path)
        logger.info("Successfully generated CSV and plot report.")
        return True
    except Exception as e:
        logger.error(f"An error occurred during CSV/Plot report generation: {e}", exc_info=True)
        return False