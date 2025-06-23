# phorest_pipeline/processor/logic.py
import datetime
import sys
import time
from pathlib import Path

from phorest_pipeline.processor.process_image import process_image
from phorest_pipeline.shared.config import (
    DATA_DIR,
    DATA_READY_FLAG,
    ENABLE_CAMERA,
    ENABLE_THERMOCOUPLE,
    PROCESSOR_INTERVAL,
    RESULTS_DIR,
    RESULTS_READY_FLAG,
    settings,  # Check if config loaded
)
from phorest_pipeline.shared.helper_utils import move_existing_files_to_backup
from phorest_pipeline.shared.logger_config import configure_logger

# Assuming metadata_manager handles loading/saving the manifest
from phorest_pipeline.shared.metadata_manager import append_metadata, load_metadata, save_metadata
from phorest_pipeline.shared.states import ProcessorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="processor.log")

METADATA_FILENAME = Path("processing_manifest.json")
RESULTS_FILENAME = Path("processing_results.json")

POLL_INTERVAL = PROCESSOR_INTERVAL / 20 if PROCESSOR_INTERVAL > (5 * 20) else 5


# Helper Function: Find next unprocessed entry
def find_unprocessed_entry(metadata_list: list) -> tuple[int, dict | None]:
    """Finds the index and data of the first entry with 'processed': False."""
    for index, entry in enumerate(metadata_list):
        if not entry.get("processed", False):  # Find first entry not marked as processed
            # Basic validation: Check if necessary data exists in entry
            if entry.get("camera_data") and entry["camera_data"].get("filename"):
                return index, entry
            elif entry.get("temperature_data"):
                # We need the image.
                logger.warning(
                    f"Entry {index} found unprocessed but missing camera data filename. Skipping."
                )
            else:
                logger.warning(f"Entry {index} found unprocessed but missing key data. Skipping.")
    return -1, None


# Main State Machine Logic
def perform_processing(current_state: ProcessorState) -> ProcessorState:
    """State machine logic for the processor."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(PROCESSOR_INTERVAL * 5)
        # Consider adding a FATAL_ERROR state for the processor too
        return current_state

    match current_state:
        case ProcessorState.IDLE:
            logger.info("IDLE -> WAITING_FOR_DATA")
            next_state = ProcessorState.WAITING_FOR_DATA
            global next_run_time
            next_run_time = time.monotonic() + PROCESSOR_INTERVAL

        case ProcessorState.WAITING_FOR_DATA:
            logger.info(f"Waiting for {PROCESSOR_INTERVAL} seconds until next cycle...")
            now = time.monotonic()
            if now >= next_run_time:
                if DATA_READY_FLAG.exists():
                    logger.info(f"Found flag {DATA_READY_FLAG}. Consuming.")
                    try:
                        DATA_READY_FLAG.unlink()
                        logger.info(f"Deleted flag {DATA_READY_FLAG}.")
                        logger.info("WAITING_FOR_DATA -> PROCESSING")
                        next_state = ProcessorState.PROCESSING
                    except (FileNotFoundError, OSError) as e:
                        logger.error(f"Could not delete flag {DATA_READY_FLAG}: {e}")
                        # Stay waiting, maybe the flag is gone or perms issue
                        time.sleep(5)
                else:
                    next_state = ProcessorState.IDLE
                    logger.info("WAITING_FOR_DATA -> IDLE")
            else:
                time.sleep(POLL_INTERVAL)

        case ProcessorState.PROCESSING:
            logger.info("--- Checking for Unprocessed Data ---")
            manifest_data = load_metadata(DATA_DIR, METADATA_FILENAME)
            entry_index, entry_to_process = find_unprocessed_entry(manifest_data)

            if entry_to_process:
                logger.info(
                    f"Found unprocessed entry at index {entry_index} (Image: {entry_to_process.get('camera_data', {}).get('filename')})"
                )

                # --- Attempt Processing ---
                image_results = None
                img_proc_error_msg = 'Camera not enabled'
                if ENABLE_CAMERA:
                    image_meta = entry_to_process.get("camera_data")
                    image_results, img_proc_error_msg = process_image(image_meta)

                temperature_data = None
                if ENABLE_THERMOCOUPLE:
                    temperature_data = entry_to_process.get("temperature_data", {})
                
                processing_timestamp = datetime.datetime.now().isoformat()
                if image_results or temperature_data:
                    processing_successful = True

                if img_proc_error_msg:
                    logger.error(f"Image processing failed: {img_proc_error_msg}")
                    # Optionally, you could set a flag or take other actions here

                # --- Aggregate Results ---
                final_result_entry = {
                    "manifest_entry_timestamp": entry_to_process.get("entry_timestamp_iso"),
                    "image_timestamp": entry_to_process.get("camera_data", {"timestamp_iso": None}).get(
                        "timestamp_iso"
                    ),
                    "temperature_timestamp": temperature_data.get("timestamp_iso") if temperature_data else None,
                    "image_filename": image_meta.get("filename") if image_meta else None,
                    "processing_timestamp_iso": processing_timestamp,
                    "processing_successful": processing_successful,
                    "processing_error_message": img_proc_error_msg,
                    "image_analysis": image_results,
                    "temperature_readings": temperature_data.get("data") if temperature_data else None,
                }

                append_metadata(RESULTS_DIR, RESULTS_FILENAME, final_result_entry)

                # --- Update Manifest ---
                entry_to_process["processed"] = True
                entry_to_process["processing_timestamp_iso"] = processing_timestamp
                entry_to_process["processing_error"] = True if img_proc_error_msg else False
                entry_to_process["processing_error_msg"] = img_proc_error_msg

                # Replace the old entry with the updated one in the list
                manifest_data[entry_index] = entry_to_process

                # Save the entire updated manifest
                save_metadata(DATA_DIR, METADATA_FILENAME, manifest_data)

                logger.info(
                    f"Processed entry index {entry_index}. Success: {True if img_proc_error_msg else False}\n\n"
                )

                # --- Stay in PROCESSING state ---
                # Immediately check for the next unprocessed entry without waiting for the flag
                next_state = ProcessorState.PROCESSING
                # Optional small delay to prevent tight loop if errors occur fast
                time.sleep(0.1)

            else:
                # No unprocessed entries found
                logger.info("No more unprocessed entries found in manifest.")
                logger.info(f"Creating flag: {RESULTS_READY_FLAG}")
                try:
                    RESULTS_READY_FLAG.touch()
                    logger.info("PROCESSING -> IDLE")
                    next_state = ProcessorState.IDLE
                except OSError as e:
                    logger.error(f"Could not create flag {RESULTS_READY_FLAG}: {e}")
                    time.sleep(5)
                    next_state = ProcessorState.PROCESSING  # Retry flag creation

        case ProcessorState.FATAL_ERROR:
            # Should not technically be called again once in this state if loop breaks
            logger.error("[FATAL ERROR] Shutting down processor.")
            time.sleep(10)  # Sleep long if it somehow gets called

    return next_state


# Main execution loop function
def run_processor():
    """Main loop for the processor process."""
    logger.info("--- Starting Processor ---")
    print("--- Starting Processor ---")
    # Start in PROCESSING state to immediately clear any backlog
    current_state = ProcessorState.PROCESSING
    global next_run_time
    next_run_time = 0

    # Initial cleanup: remove data flag if it exists on startup
    if settings:
        files_to_move = [Path(RESULTS_DIR, RESULTS_FILENAME)]
        move_existing_files_to_backup(files_to_move, logger=logger)
        logger.info("Moved existing files to backup directory.")
        try:
            DATA_READY_FLAG.unlink(missing_ok=True)
            logger.info(f"Ensured flag {DATA_READY_FLAG} is initially removed.")
        except OSError as e:
            logger.warning(f"Could not remove initial flag {DATA_READY_FLAG}: {e}")

    try:
        while True:
            current_state = perform_processing(current_state)

            # --- Check for FATAL_ERROR state to exit ---
            if current_state == ProcessorState.FATAL_ERROR:
                logger.info("Exiting due to FATAL_ERROR state.")
                break  # Exit the while loop

            # Sleep only when waiting, processing loop handles its own pacing/delays
            if (
                current_state == ProcessorState.WAITING_FOR_DATA
                or current_state == ProcessorState.IDLE
            ):
                time.sleep(0.1)  # Prevent busy-looping when idle/waiting
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR in main loop: {e}")
        current_state = ProcessorState.FATAL_ERROR
    finally:
        # No flags need specific cleanup here unless DATA_READY might be left mid-operation
        if settings:
            logger.info("Cleaning up flags...")
            try:
                DATA_READY_FLAG.unlink(missing_ok=True)
            except OSError as e:
                logger.error(f"Could not clean up flag {DATA_READY_FLAG} on exit: {e}")
        logger.info("--- Processor Stopped ---")
        print("--- Processor Stopped ---")
        if current_state == ProcessorState.FATAL_ERROR:
            sys.exit(1)
        else:
            sys.exit(0)
