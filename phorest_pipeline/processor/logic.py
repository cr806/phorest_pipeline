# phorest_pipeline/processor/logic.py
import datetime
from email.mime import image
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
from phorest_pipeline.shared.metadata_manager import (
    append_metadata,
    load_metadata_with_lock,
    update_metatdata_manifest_entry_status,
)
from phorest_pipeline.shared.states import ProcessorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="processor.log")

METADATA_FILENAME = Path("metadata_manifest.json")
RESULTS_FILENAME = Path("processing_results.json")

POLL_INTERVAL = PROCESSOR_INTERVAL / 20 if PROCESSOR_INTERVAL > (5 * 20) else 5

# Global variable to store the entry being processed outside of the lock
_current_processing_entry_data: dict | None = None
_current_processing_entry_index: int = -1

# Helper Function: Find next unprocessed entry
def find_unprocessed_entry(metadata_list: list) -> tuple[int, dict | None]:
    """
    Finds the index and data of the first entry with 'processing_status': 'pending'.
    Also logs warnings for 'processing' or other unexpected statuses.
    """
    for index, entry in enumerate(metadata_list):
        status = entry.get("processing_status", "unknown") # Default to 'unknown' if not set
        if status == "pending":
            # Basic validation: Check if necessary data exists in entry
            if entry.get("camera_data") and entry["camera_data"].get("filename"):
                return index, entry
            # Special case: If only temperature data is expected, handle it
            elif not ENABLE_CAMERA and ENABLE_THERMOCOUPLE and entry.get("temperature_data"):
                return index, entry
            else:
                logger.warning(
                    f"Entry {index} found with status '{status}' but missing required data (camera filename or temp data if camera disabled). Skipping."
                )
        elif status == "processing":
            # This indicates a previous crash or a long-running task.
            # Possibly re-evaluate these after a timeout.
            logger.warning(f"Entry {index} found with status 'processing'. It might be stuck or still being processed by another instance. Skipping for now.")
    return -1, None


# Main State Machine Logic
def perform_processing(current_state: ProcessorState) -> ProcessorState:
    """State machine logic for the processor."""
    next_state = current_state
    global _current_processing_entry_data, _current_processing_entry_index

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return ProcessorState.FATAL_ERROR

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
            # 1. Acquire lock, mark entry as 'processing'
            if _current_processing_entry_data is None:
                logger.info("--- Checking for PENDING Data to Process ---")
                try:
                    manifest_data = load_metadata_with_lock(DATA_DIR, METADATA_FILENAME)
                    entry_index, entry_to_process = find_unprocessed_entry(manifest_data)

                    if entry_to_process:
                        _current_processing_entry_index = entry_index
                        _current_processing_entry_data = entry_to_process.copy()
                
                        logger.info(
                            f"Marking entry {entry_index} as 'processing' (Image: {_current_processing_entry_data.get('camera_data', {}).get('filename')})"
                        )

                        update_metatdata_manifest_entry_status(
                            DATA_DIR, METADATA_FILENAME,
                            _current_processing_entry_index,
                            'processing',
                            processing_timestamp_iso=datetime.datetime.now().isoformat()
                        )
                        logger.info(f"Successfully marked entry {entry_index} as 'processing'.")
                    else:
                        logger.info("No more PENDING entries found in manifest.")
                        logger.info(f"Creating flag: {RESULTS_READY_FLAG}")
                        try:
                            RESULTS_READY_FLAG.touch()
                            logger.info("PROCESSING -> IDLE")
                            next_state = ProcessorState.IDLE
                        except OSError as e:
                            logger.error(f"Could not create flag {RESULTS_READY_FLAG}: {e}")
                            time.sleep(5)
                            next_state = ProcessorState.PROCESSING
                except Exception as e:
                    logger.error(f"Error during manifest read/mark phase: {e}")
                    _current_processing_entry_data = None # Reset
                    _current_processing_entry_index = -1
                    time.sleep(POLL_INTERVAL)
                    next_state = ProcessorState.PROCESSING
            
            # 2. Process the entry (outside of file lock)
            if _current_processing_entry_data is not None:
                logger.info(f"Performing processing for entry {_current_processing_entry_index} (Image: {_current_processing_entry_data.get('camera_data', {}).get('filename')})...")

                image_results = None
                img_proc_error_msg = None 
                processing_successful = False
                
                try:
                    if ENABLE_CAMERA:
                        image_meta = _current_processing_entry_data.get("camera_data")
                        if image_meta and image_meta.get("filename"):
                            image_results, img_proc_error_msg = process_image(image_meta)
                        else:
                            img_proc_error_msg = "Camera enabled but no image data or filename found in entry."
                            logger.warning(img_proc_error_msg)
                            image_results = None # Ensure no partial results
                    else:
                        img_proc_error_msg = 'Camera not enabled, skipping image processing.'

                    temperature_data = None
                    if ENABLE_THERMOCOUPLE:
                        temperature_data = _current_processing_entry_data.get("temperature_data", {})
                    else:
                        logger.info("Temperature collection not enabled, skipping temperature data.")

                    if (ENABLE_CAMERA and image_results) or (ENABLE_THERMOCOUPLE and temperature_data):
                        processing_successful = True
                    elif ENABLE_CAMERA and img_proc_error_msg: # If camera was enabled but failed
                        processing_successful = False
                    elif not ENABLE_CAMERA and not ENABLE_THERMOCOUPLE: # If neither enabled, nothing to process
                         processing_successful = False
                         img_proc_error_msg = "Neither camera nor thermocouple enabled for processing."

                    if not processing_successful and img_proc_error_msg:
                        img_proc_error_msg = "Processing failed for unknown reason, no successful results."
                        logger.error(f"Image processing failed: {img_proc_error_msg}")

                    # --- Aggregate Results ---
                    final_result_entry = {
                        "manifest_entry_timestamp": _current_processing_entry_data.get("entry_timestamp_iso"),
                        "image_timestamp": image_meta.get("timestamp_iso") if image_meta else None,
                        "temperature_timestamp": temperature_data.get("timestamp_iso") if temperature_data else None,
                        "image_filename": image_meta.get("filename") if image_meta else None,
                        "processing_timestamp_iso": datetime.datetime.now().isoformat(),
                        "processing_successful": processing_successful,
                        "processing_error_message": img_proc_error_msg,
                        "image_analysis": image_results,
                        "temperature_readings": temperature_data.get("data") if temperature_data else None,
                    }

                    append_metadata(RESULTS_DIR, RESULTS_FILENAME, final_result_entry)
                    logger.info(f"Appended results to {RESULTS_FILENAME.name} for entry {_current_processing_entry_index}. Success: {processing_successful}")
                    if processing_successful:
                        logger.info(f"Processing completed successfully for entry {_current_processing_entry_index}.")
                except Exception as e:
                    logger.error(f"Critical error during image processing for entry {_current_processing_entry_index}: {e}", exc_info=True)
                    img_proc_error_msg = f"Critical processing error: {e}"
                    processing_successful = False
                    image_results = None # Clear results if error occurred
                    temperature_data = None # Clear data if error occurred

                # 3. Acquire lock, update manifest with final status and results
                logger.info(f"Updating manifest for entry {_current_processing_entry_index}...")
                update_metatdata_manifest_entry_status(
                    DATA_DIR, METADATA_FILENAME,
                    _current_processing_entry_index,
                    'processed' if processing_successful else 'failed',
                    processing_timestamp_iso=datetime.datetime.now().isoformat(),
                    processing_error=not processing_successful,
                    processing_error_msg=img_proc_error_msg,
                    image_analysis_results=image_results,
                    temperature_processing_results=temperature_data.get('data') if temperature_data else None,
                )
                logger.info(f"Manifest entry {_current_processing_entry_index} updated with final status and results.")

                # Reset global state for next cycle
                _current_processing_entry_data = None
                _current_processing_entry_index = -1

                next_state = ProcessorState.PROCESSING # Immediately check for next entry

            else:
                logger.info("No entry selected for processing. Transitioning out of PROCESSING state.")
                next_state = ProcessorState.IDLE # Or WAITING_FOR_DATA
                # The RESULTS_READY_FLAG is handled in the `if entry_to_process:` block (inverted if statement)


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
            logger.info("Performing final cleanup of temporary files...")
            results_temp_path = Path(RESULTS_DIR, RESULTS_FILENAME).with_suffix(RESULTS_FILENAME.suffix + '.tmp')
            if results_temp_path.exists():
                try:
                    results_temp_path.unlink()
                    logger.info(f"Cleaned up {results_temp_path.name} on shutdown.")
                except OSError as e:
                    logger.error(f"Could not clean up {results_temp_path.name} on shutdown: {e}")

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
