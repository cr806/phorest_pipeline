# process_pipeline/collector/logic.py
import datetime
import signal
import sys
import time
from pathlib import Path

from phorest_pipeline.collector.sources.thermocouple_controller import thermocouple_controller
from phorest_pipeline.shared.config import (
    COLLECTOR_INTERVAL,
    DATA_DIR,
    DATA_READY_FLAG,
    ENABLE_CAMERA,
    ENABLE_THERMOCOUPLE,
    FAILURE_LIMIT,
    FLAG_DIR,
    IMAGE_BUFFER_SIZE,
    METADATA_FILENAME,
    RETRY_DELAY,
    settings,  # Import settings to check if config loaded ok
)
from phorest_pipeline.shared.helper_utils import (
    move_existing_files_to_backup,
    ring_buffer_cleanup,
    snapshot_configs,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import add_entry, update_service_heartbeat
from phorest_pipeline.shared.states import CollectorState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="collector.log")

if ENABLE_CAMERA:
    from phorest_pipeline.shared.config import CAMERA_TYPE
    from phorest_pipeline.shared.image_sources import ImageSourceType

    if CAMERA_TYPE == ImageSourceType.LOGITECH:
        from phorest_pipeline.collector.sources.logi_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.ARGUS:
        from phorest_pipeline.collector.sources.argus_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.TIS:
        from phorest_pipeline.collector.sources.tis_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.HAWKEYE:
        from phorest_pipeline.collector.sources.hawkeye_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.DUMMY:
        from phorest_pipeline.collector.sources.dummy_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.FILE_IMPORTER:
        from phorest_pipeline.collector.sources.image_file_importer import (
            image_file_importer as camera_controller,
        )
    logger.info(f"Camera type: {CAMERA_TYPE}")

SCRIPT_NAME = "phorest-collector"

POLL_INTERVAL = COLLECTOR_INTERVAL / 5


class Collector:
    """Encapsulates the state and logic for the data collector."""

    def __init__(self):
        self.shutdown_requested = False
        self.current_state = CollectorState.IDLE
        self.next_run_time = 0
        self.failure_count = 0

        # Register the signal handler
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, _signum, _frame):
        """Signal handler to initiate a graceful shutdown"""
        if not self.shutdown_requested:
            logger.info("Shutdown signal received. Finishing current cycle before stopping...")
            self.shutdown_requested = True

    def _perform_collection(self):
        """State machine logic for the collector."""

        if settings is None:
            logger.error("Configuration error. Halting.")
            time.sleep(POLL_INTERVAL * 5)
            self.current_state = CollectorState.FATAL_ERROR  # Exit on config error
            return

        match self.current_state:
            case CollectorState.IDLE:
                logger.debug("IDLE -> WAITING_TO_RUN")
                self.next_run_time = time.monotonic() + COLLECTOR_INTERVAL
                self.current_state = CollectorState.WAITING_TO_RUN

            case CollectorState.WAITING_TO_RUN:
                now = time.monotonic()
                if now >= self.next_run_time:
                    logger.debug("WAITING_TO_RUN -> COLLECTING")
                    self.failure_count = 0  # Reset failure count when *entering* COLLECTING state
                    self.current_state = CollectorState.COLLECTING
                else:
                    time.sleep(POLL_INTERVAL)

            case CollectorState.COLLECTING:
                logger.info("--- Running Collection ---")
                logger.info(f"Collection Attempt {self.failure_count + 1}/{FAILURE_LIMIT}")

                cam_metadata_for_entry = None
                temps_metadata_for_entry = None

                if ENABLE_CAMERA:
                    logger.debug("Camera is enabled.")
                    try:
                        cam_status, cam_msg, cam_data_from_controller = camera_controller(DATA_DIR)
                        if cam_status == 0:
                            cam_metadata_for_entry = cam_data_from_controller
                            logger.info(
                                f"Camera data collected: {cam_metadata_for_entry.get('filename')}"
                            )
                        else:
                            # Explicitly create error metadata
                            cam_metadata_for_entry = {
                                "error_flag": True,
                                "error_message": cam_msg,
                                "filename": cam_data_from_controller.get("filename")
                                if cam_data_from_controller
                                else None,
                                "timestamp_iso": cam_data_from_controller.get("timestamp_iso")
                                if cam_data_from_controller
                                else datetime.datetime.now().isoformat(),
                            }
                            logger.error(f"Camera collection failed: {cam_msg}")
                    except Exception as e:
                        error_msg = f"Unexpected error during camera collection: {e}"
                        logger.error(error_msg, exc_info=True)
                        cam_metadata_for_entry = {
                            "error_flag": True,
                            "error_message": error_msg,
                            "filename": None,  # Explicitly no filename on unexpected crash
                            "timestamp_iso": datetime.datetime.now().isoformat(),  # Timestamp for the error
                        }
                else:
                    logger.info("Camera not enabled. Skipping image capture.")

                if ENABLE_THERMOCOUPLE:
                    logger.debug("Thermocouple is enabled.")
                    try:
                        tc_status, tc_msg, tc_data_from_controller = thermocouple_controller()
                        if tc_status == 0:
                            temps_metadata_for_entry = tc_data_from_controller
                            if "error_flag" not in temps_metadata_for_entry:
                                temps_metadata_for_entry["error_flag"] = False
                                temps_metadata_for_entry["error_message"] = None
                            logger.info("Thermocouple data collected")
                        else:
                            temps_metadata_for_entry = {
                                "error_flag": True,
                                "error_message": tc_msg,
                                "data": tc_data_from_controller.get("data")
                                if tc_data_from_controller
                                else None,
                                "timestamp_iso": tc_data_from_controller.get("timestamp_iso")
                                if tc_data_from_controller
                                else datetime.datetime.now().isoformat(),
                            }
                            logger.error(f"Thermocouple collection failed: {tc_msg}")
                    except Exception as e:
                        error_msg = f"Unexpected error during thermocouple collection: {e}"
                        logger.error(error_msg, exc_info=True)
                        temps_metadata_for_entry = {
                            "error_flag": True,
                            "error_message": error_msg,
                            "data": None,  # Explicitly no data on unexpected crash
                            "timestamp_iso": datetime.datetime.now().isoformat(),  # Timestamp for the error
                        }
                else:
                    logger.info("Thermocouple not enabled. Skipping temperature capture.")

                if not ENABLE_CAMERA and not ENABLE_THERMOCOUPLE:
                    logger.info("No components enabled. Skipping flag creation and buffer.")
                    self.current_state = CollectorState.IDLE
                    return

                # --- Add entry to the metadata manifest ---
                current_collection_successful = True

                if ENABLE_CAMERA and (
                    cam_metadata_for_entry is None
                    or cam_metadata_for_entry.get("error_flag", True)
                ):
                    current_collection_successful = False
                if ENABLE_THERMOCOUPLE and (
                    temps_metadata_for_entry is None
                    or temps_metadata_for_entry.get("error_flag", True)
                ):
                    current_collection_successful = False

                try:
                    add_entry(
                        manifest_path=Path(DATA_DIR, METADATA_FILENAME),
                        camera_meta=cam_metadata_for_entry,
                        temps_meta=temps_metadata_for_entry,
                    )
                    logger.debug("Entry added to processing manifest.")
                    self.failure_count = 0  # Reset failure count on successful manifest write
                except Exception as e:
                    logger.critical(
                        f"Failed to add entry to processing manifest: {e}. This indicates a serious issue with file locking/writing.",
                        exc_info=True,
                    )
                    current_collection_successful = False
                    self.failure_count += 1  # Increment failure count for manifest write failure

                if current_collection_successful:
                    if CAMERA_TYPE == ImageSourceType.FILE_IMPORTER:
                        logger.info("Image File import conplete. Collector will now halt.")
                        self.shutdown_requested = True  # Signal for a clean stop
                        return

                    if IMAGE_BUFFER_SIZE > 0:
                        ring_buffer_cleanup(logger=logger)

                    logger.debug(f"Creating flag: {DATA_READY_FLAG}")
                    try:
                        DATA_READY_FLAG.touch()
                        logger.info("--- Collection Cycle Done ---")
                        logger.debug("COLLECTING -> IDLE")
                        self.current_state = CollectorState.IDLE
                    except OSError as e:
                        logger.critical(
                            f"Could not create flag {DATA_READY_FLAG}: {e}. This will prevent processor from starting. Transitioning to FATAL_ERROR.",
                            exc_info=True,
                        )
                        time.sleep(POLL_INTERVAL)
                        self.current_state = CollectorState.FATAL_ERROR
                else:
                    logger.warning(
                        "Data collection cycle finished with errors or manifest write failed."
                    )
                    self.failure_count += 1  # Increment failure count
                    logger.debug(f"Failure count: {self.failure_count}/{FAILURE_LIMIT}")

                    if self.failure_count >= FAILURE_LIMIT:
                        logger.critical(f"[FATAL ERROR] Reached failure limit ({FAILURE_LIMIT}).")
                        self.current_state = CollectorState.FATAL_ERROR
                    else:
                        # Stay in COLLECTING state to retry immediately
                        logger.debug("Retrying collection...")
                        self.current_state = CollectorState.COLLECTING
                        logger.debug(f"Waiting {RETRY_DELAY}s before retrying...")
                        time.sleep(RETRY_DELAY)

            case CollectorState.FATAL_ERROR:
                # Should not technically be called again once in this state if loop breaks
                logger.error("[FATAL ERROR] Shutting down collector.")
                time.sleep(10)  # Sleep long if it somehow gets called

    def run(self):
        """Main loop for the collector process."""
        logger.info("--- Starting Collector ---")
        print("--- Starting Collector ---")

        # Initial cleanup: remove data ready flag if it exists on startup
        if settings:
            snapshot_configs(logger=logger)
            
            files_to_move = [Path(DATA_DIR, METADATA_FILENAME)]
            move_existing_files_to_backup(files_to_move, logger=logger)
            logger.info("Moved existing files to backup directory.")
            try:
                DATA_READY_FLAG.unlink(missing_ok=True)
                logger.debug(f"Ensured flag {DATA_READY_FLAG} is initially removed.")
            except OSError as e:
                logger.warning(f"Could not remove initial flag {DATA_READY_FLAG}: {e}")

        try:
            while not self.shutdown_requested:
                self._perform_collection()

                # After a cycle is complete, send a heartbeat.
                update_service_heartbeat(SCRIPT_NAME, FLAG_DIR)

                # --- Check for FATAL_ERROR state to exit ---
                if self.current_state == CollectorState.FATAL_ERROR:
                    logger.error("Exiting due to FATAL_ERROR state.")
                    break  # Exit the while loop

                # Small sleep even in fast transitions to prevent busy-looping if logic is instant
                if self.current_state != CollectorState.WAITING_TO_RUN:
                    time.sleep(0.1)
        except Exception as e:
            logger.critical(f"UNEXPECTED ERROR in main loop: {e}", exc_info=True)
            self.current_state = CollectorState.FATAL_ERROR
        finally:
            # Cleanup on exit
            if settings:
                logger.info("Cleaning up flags...")
                try:
                    DATA_READY_FLAG.unlink(missing_ok=True)
                except OSError as e:
                    logger.error(f"Could not clean up flag {DATA_READY_FLAG} on exit: {e}")
            logger.info("--- Collector Stopped ---")
            print("--- Collector Stopped ---")
            if self.current_state == CollectorState.FATAL_ERROR and not self.shutdown_requested:
                sys.exit(1)
            else:
                sys.exit(0)


def run_collector():
    """Main entry point to create and run a Collector instance"""
    collector = Collector()
    collector.run()
