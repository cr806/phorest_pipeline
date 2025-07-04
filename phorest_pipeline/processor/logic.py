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
    METADATA_FILENAME,
    PROCESSOR_INTERVAL,
    RESULTS_DIR,
    RESULTS_FILENAME,
    RESULTS_READY_FLAG,
    settings,  # Check if config loaded
)
from phorest_pipeline.shared.helper_utils import move_existing_files_to_backup
from phorest_pipeline.shared.logger_config import configure_logger

# Assuming metadata_manager handles loading/saving the manifest
from phorest_pipeline.shared.metadata_manager import (
    append_metadata,
    load_metadata_with_lock,
    update_metadata_manifest_entry,
)
from phorest_pipeline.shared.states import ProcessorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="processor.log")

POLL_INTERVAL = PROCESSOR_INTERVAL / 20 if PROCESSOR_INTERVAL > (5 * 20) else 5

# Global variable to store the entry being processed outside of the lock
_current_processing_entry_data: dict | None = None
_current_processing_entry_index: int = -1

# Helper Function: Find next unprocessed entry
def find_all_unprocessed_entries(metadata_list: list) -> list[tuple[int, dict]]:
    """
    Finds the index and data of all entries with 'processing_status': 'pending'.
    Returns a list of tuples (index, entry_data).
    """
    entries_to_process = []
    for index, entry in enumerate(metadata_list):
        status = entry.get("processing_status", "unknown")
        if status == "pending":
            # You can add the same validation as before
            if entry.get("camera_data") and entry["camera_data"].get("filename"):
                entries_to_process.append((index, entry))
            elif not ENABLE_CAMERA and ENABLE_THERMOCOUPLE and entry.get("temperature_data"):
                 entries_to_process.append((index, entry))
            else:
                logger.warning(
                    f"Entry {index} found with status 'pending' but missing required data. Skipping."
                )
        elif status == "processing":
            logger.warning(f"Entry {index} found with status 'processing'. It might be stuck. Skipping for now.")

    return entries_to_process


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
            global next_run_time
            next_run_time = time.monotonic() + PROCESSOR_INTERVAL
            logger.info(f"Next run time set to {next_run_time} (in {PROCESSOR_INTERVAL} seconds).")
            next_state = ProcessorState.WAITING_FOR_DATA

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
            pending_batch = []
                
            # 1. Acquire lock ONCE, find all pending entries, and mark them all as 'processing'.
            logger.info("--- Checking for PENDING Data to Process ---")
            try:
                manifest_data = load_metadata_with_lock(DATA_DIR, METADATA_FILENAME)
                pending_batch = find_all_unprocessed_entries(manifest_data)

                if pending_batch:
                    indices_to_mark = [index for index, entry in pending_batch]
                    logger.info(f"Found batch of {len(pending_batch)} entries to process. Marking as 'processing': {indices_to_mark}")
                    
                    update_metadata_manifest_entry(
                        DATA_DIR,
                        METADATA_FILENAME,
                        entry_index=indices_to_mark,
                        status='processing',
                        processing_timestamp_iso=datetime.datetime.now().isoformat()
                    )
                else:
                    logger.info("No more PENDING entries found in manifest.")
                    logger.info("PROCESSING -> IDLE")
                    next_state = ProcessorState.IDLE
                    # Ensure flag is present
                    try:
                        RESULTS_READY_FLAG.touch()
                    except OSError as e:
                        logger.error(f"Could not create flag {RESULTS_READY_FLAG}: {e}")
                    return next_state

            except Exception as e:
                logger.error(f"Error during manifest read/mark phase: {e}", exc_info=True)
                time.sleep(POLL_INTERVAL)
                next_state = ProcessorState.PROCESSING # Retry finding entries
                return next_state


            # 2. Process the entire batch (outside of the file lock)
            if pending_batch:
                logger.info(f"--- Starting processing for batch of {len(pending_batch)} entries ---")
                all_results_for_manifest_update = []
                all_results_for_append = []

                for entry_index, entry_data in pending_batch:
                    logger.info(f"Processing entry {entry_index} (Image: {entry_data.get('camera_data', {}).get('filename')})...")
                    image_results, img_proc_error_msg, processing_successful = None, None, False

                    try:
                        if ENABLE_CAMERA:
                            image_meta = entry_data.get("camera_data")
                            if image_meta and image_meta.get("filename"):
                                image_results, img_proc_error_msg = process_image(image_meta)
                            else:
                                img_proc_error_msg = "Camera enabled but no image data or filename found in entry."
                        else:
                            img_proc_error_msg = 'Camera not enabled, skipping image processing.'

                        temperature_data = entry_data.get("temperature_data", {}) if ENABLE_THERMOCOUPLE else None
                        
                        if (ENABLE_CAMERA and image_results) or (ENABLE_THERMOCOUPLE and temperature_data and not temperature_data.get('error_flag')):
                            processing_successful = True

                        if not processing_successful and not img_proc_error_msg:
                            img_proc_error_msg = "Processing failed for an unknown reason."
                        
                        logger.info(f"Finished processing entry {entry_index}. Success: {processing_successful}")

                        # --- Aggregate results for this single entry ---
                        final_result_entry = {
                            "manifest_entry_timestamp": entry_data.get("entry_timestamp_iso"),
                            "image_timestamp": image_meta.get("timestamp_iso") if image_meta else None,
                            "temperature_timestamp": temperature_data.get("timestamp_iso") if temperature_data else None,
                            "image_filename": image_meta.get("filename") if image_meta else None,
                            "processing_timestamp_iso": datetime.datetime.now().isoformat(),
                            "processing_successful": processing_successful,
                            "processing_error_message": img_proc_error_msg,
                            "image_analysis": image_results,
                            "temperature_readings": temperature_data.get("data") if temperature_data else None,
                        }
                        all_results_for_append.append(final_result_entry)

                        # --- Store data needed for the final manifest update ---
                        all_results_for_manifest_update.append({
                            'index': entry_index,
                            'status': 'processed' if processing_successful else 'failed',
                            'error_msg': img_proc_error_msg,
                        })

                    except Exception as e:
                        logger.error(f"Critical error during image processing for entry {entry_index}: {e}", exc_info=True)
                        # Log failure for this specific entry and continue with the batch
                        all_results_for_manifest_update.append({
                            'index': entry_index,
                            'status': 'failed',
                            'error_msg': f"Critical processing error: {e}",
                        })

                # 3. Collate results and perform a single batch update
                logger.info("--- Collating results for batch update ---")

                # Append collated results to the results.json file
                try:
                    if all_results_for_append:
                        append_metadata(RESULTS_DIR, RESULTS_FILENAME, all_results_for_append)
                except Exception as e:
                    logger.error(f"Error appending to results file: {e}", exc_info=True)


                # Prepare lists for the single manifest update call
                if all_results_for_manifest_update:
                    indices_to_update = [res['index'] for res in all_results_for_manifest_update]
                    updated_statues = [res['status'] for res in all_results_for_manifest_update]
                    updated_error_msgs = [res['error_msg'] for res in all_results_for_manifest_update]
                    
                    try:
                        update_metadata_manifest_entry(
                            DATA_DIR,
                            METADATA_FILENAME,
                            indices_to_update,
                            status=updated_statues,
                            processing_timestamp_iso=datetime.datetime.now().isoformat(), # Apply same timestamp to whole batch
                            processing_error=[s == 'failed' for s in updated_statues],
                            processing_error_msg=updated_error_msgs,
                        )
                        logger.info(f"Successfully performed batch update on manifest for {len(indices_to_update)} entries.")

                        logger.info(f"Creating results ready flag: {RESULTS_READY_FLAG}")
                        try:
                            RESULTS_READY_FLAG.touch()
                        except OSError as e:
                            logger.error(f"Could not create results ready flag {RESULTS_READY_FLAG}: {e}")

                    except Exception as e:
                        logger.error(f"Critical error during final batch update of manifest: {e}", exc_info=True)

            # Loop back immediately to check for more data
            next_state = ProcessorState.PROCESSING
        
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
        if Path(RESULTS_DIR, RESULTS_FILENAME).exists():
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
