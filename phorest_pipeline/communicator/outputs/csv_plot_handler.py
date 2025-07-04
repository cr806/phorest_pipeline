from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from phorest_pipeline.shared.config import (
    ENABLE_CAMERA,
    ENABLE_THERMOCOUPLE,
    RESULTS_DIR,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import lock_and_manage_file

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="comms_csv_plot.log")

CSV_FILENAME = Path("communicating_results.csv")
RESULTS_IMAGE = Path("processed_data_plot.png")


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

    ax[0].legend(loc="upper left")

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