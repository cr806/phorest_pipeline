# src/process_pipeline/communicator/logic.py
import signal
import sys
import time
from pathlib import Path

from phorest_pipeline.shared.communication_methods import CommunicationMethod
from phorest_pipeline.shared.config import (
    COMMUNICATION_METHOD,
    COMMUNICATOR_INTERVAL,
    CSV_FILENAME,
    IMAGE_FILENAME,
    RESULTS_DIR,
    RESULTS_FILENAME,
    RESULTS_READY_FLAG,
    settings,
)
from phorest_pipeline.shared.helper_utils import move_existing_files_to_backup
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import (
    load_metadata_with_lock,
    save_metadata_with_lock,
)
from phorest_pipeline.shared.states import CommunicatorState

from .outputs.csv_plot_handler import generate_report

# from .outputs.opc_ua_handler import send_data

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="comms.log")

POLL_INTERVAL = COMMUNICATOR_INTERVAL / 20 if COMMUNICATOR_INTERVAL > (5 * 20) else 5

COMMUNICATION_DISPATCH_MAP = {
    CommunicationMethod.CSV_PLOT: generate_report,
    # CommunicationMethod.OPC_UA: send_data,
}


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


class Communicator:
    """Encapsulates the state and logic for the communicator process"""

    def __init__(self):
        self.shutdown_requested = False
        self.current_state = CommunicatorState.COMMUNICATING
        self.next_run_time = 0

        # Register the signal handler
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, _signum, _frame):
        """Signal handler to initiate a graceful shutdown"""
        if not self.shutdown_requested:
            logger.info("Shutdown signal received. Finishing current cycle before stopping...")
            self.shutdown_requested = True

    def perform_communication(self):
        """State machine logic for the communicator."""

        if settings is None:
            logger.info("Configuration error. Halting.")
            time.sleep(POLL_INTERVAL * 5)
            self.current_state = CommunicatorState.FATAL_ERROR
            return

        match self.current_state:
            case CommunicatorState.IDLE:
                logger.info("IDLE -> WAITING_FOR_RESULTS")
                self.next_run_time = time.monotonic() + COMMUNICATOR_INTERVAL
                logger.info(
                    f"Will now wait for {COMMUNICATOR_INTERVAL} seconds until next cycle..."
                )
                self.current_state = CommunicatorState.WAITING_FOR_RESULTS

            case CommunicatorState.WAITING_FOR_RESULTS:
                now = time.monotonic()
                if now >= self.next_run_time:
                    if RESULTS_READY_FLAG.exists():
                        logger.info(f"Found flag {RESULTS_READY_FLAG}.")
                        # Consume the flag
                        try:
                            RESULTS_READY_FLAG.unlink()
                            logger.info(f"Deleted flag {RESULTS_READY_FLAG}.")
                            logger.info("WAITING_FOR_RESULTS -> COMMUNICATING")
                            self.current_state = CommunicatorState.COMMUNICATING
                        except FileNotFoundError:
                            logger.info("Flag disappeared before deletion. Re-checking...")
                            self.current_state = CommunicatorState.WAITING_FOR_RESULTS
                        except OSError as e:
                            logger.error(f"Could not delete flag {RESULTS_READY_FLAG}: {e}")
                            self.current_state = CommunicatorState.WAITING_FOR_RESULTS
                            time.sleep(POLL_INTERVAL)
                    else:
                        self.current_state = CommunicatorState.IDLE
                        logger.info("WAITING_FOR_RESULTS -> IDLE")
                else:
                    time.sleep(POLL_INTERVAL)

            case CommunicatorState.COMMUNICATING:
                logger.info("--- Running Communication ---")
                communication_successful = False
                try:
                    results_data = load_metadata_with_lock(Path(RESULTS_DIR, RESULTS_FILENAME))
                    entries_to_process = find_processed_entries(results_data)

                    if not entries_to_process:
                        logger.info("No new entries to communicate.")
                        self.current_state = CommunicatorState.IDLE
                        return

                    logger.info(
                        f"Found {len(entries_to_process)} processed entries to communicate."
                    )

                    handler_function = COMMUNICATION_DISPATCH_MAP.get(COMMUNICATION_METHOD)
                    if handler_function:
                        logger.info(f"Using {COMMUNICATION_METHOD.name} communication handler.")
                        communication_successful = handler_function(entries_to_process)
                    else:
                        logger.error(
                            f"Handler for communication method '{COMMUNICATION_METHOD.name}' not found or not implemented."
                        )
                        communication_successful = False

                    if communication_successful:
                        logger.info("Communication successful. Marking entries as transmitted.")
                        indices_to_mark = find_not_transmitted_entries_indices(results_data)
                        for index in indices_to_mark:
                            if 0 <= index < len(results_data):
                                results_data[index]["data_transmitted"] = True
                            else:
                                logger.warning(
                                    f"Attempted to mark non-existent entry at index {index} as transmitted. Data inconsistency?"
                                )
                        save_metadata_with_lock(Path(RESULTS_DIR, RESULTS_FILENAME), results_data)
                    else:
                        logger.error("Communication method failed.  Will retry later.")

                except Exception as e:
                    logger.error(f"Error during COMMUNICATING state: {e}", exc_info=True)
                    # If loading fails, or any part of communication, retry after a delay
                    self.current_state = (
                        CommunicatorState.COMMUNICATING
                    )  # Stay in COMMUNICATING to retry
                    time.sleep(POLL_INTERVAL * 5)
                    return

                logger.info("COMMUNICATING -> IDLE")
                self.current_state = CommunicatorState.IDLE

            case CommunicatorState.FATAL_ERROR:
                logger.error("[FATAL ERROR] Shutting down communicator.")
                time.sleep(10)  # Prevent busy-looping in fatal state

    def run(self):
        """Main loop for the communicator process."""
        logger.info("--- Starting Communicator ---")
        print("--- Starting Communicator ---")

        # Initial cleanup: remove results flag if it exists on startup
        if settings:
            files_to_move = [Path(RESULTS_DIR, CSV_FILENAME), Path(RESULTS_DIR, IMAGE_FILENAME)]
            move_existing_files_to_backup(files_to_move, logger=logger)
            logger.info("Moved existing files to backup directory.")
            try:
                RESULTS_READY_FLAG.unlink(missing_ok=True)
                logger.info(f"Ensured flag {RESULTS_READY_FLAG} is initially removed.")
            except OSError as e:
                logger.warning(f"Could not remove initial flag {RESULTS_READY_FLAG}: {e}")

        try:
            while not self.shutdown_requested:
                self._perform_communication()
                if self.current_state == CommunicatorState.FATAL_ERROR:
                    logger.error("Exiting due to FATAL_ERROR state.")
                    break
                time.sleep(0.1)  # Small sleep to prevent busy-looping
        except Exception as e:
            logger.critical(f"UNEXPECTED ERROR in main loop: {e}", exc_info=True)
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
            if self.current_state == CommunicatorState.FATAL_ERROR and not self.shutdown_requested:
                sys.exit(1)  # Exit with error code if fatal
            else:
                sys.exit(0)  # Exit cleanly


def run_communicator():
    """ Main entry point to create and run a Communicator instance """
    communicator = Communicator()
    communicator.run()