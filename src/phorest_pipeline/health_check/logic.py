# src/phorest_pipeline/health_checker/logic.py
import datetime
import json
import signal
import subprocess
import time
from collections import deque
from pathlib import Path

import matplotlib.pyplot as plt

from phorest_pipeline.shared.config import (
    COLLECTOR_INTERVAL,
    COMMUNICATOR_INTERVAL,
    COMPRESSOR_INTERVAL,
    ENABLE_HEALTH_CHECK,
    FILE_BACKUP_INTERVAL,
    FLAG_DIR,
    LOGS_DIR,
    PROCESSOR_INTERVAL,
    RESULTS_DIR,
    STATUS_FILENAME,
    SYNC_INTERVAL,
    settings,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import lock_and_manage_file
from phorest_pipeline.shared.states import HealthCheckerState  # Assuming you add this

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="health_checker.log")

# --- Configuration ---
HEALTH_CHECK_INTERVAL = 30  # Check every 10 minutes by default
POLL_INTERVAL = 10
REPORT_FILENAME = Path("health_report.png")

# Map service names to their log files and intervals
SERVICE_CONFIG = {
    "phorest-collector": {"log": "collector.log", "interval": COLLECTOR_INTERVAL},
    "phorest-processor": {"log": "processor.log", "interval": PROCESSOR_INTERVAL},
    "phorest-communicator": {"log": "comms.log", "interval": COMMUNICATOR_INTERVAL},
    "phorest-compressor": {"log": "compressor.log", "interval": COMPRESSOR_INTERVAL},
    "phorest-backup": {"log": "file_backup.log", "interval": FILE_BACKUP_INTERVAL},
    "phorest-syncer": {"log": "syncer.log", "interval": SYNC_INTERVAL},
}


def is_pid_active(pid: int | None, expected_name: str) -> bool:
    """
    Checks if a given PID is active AND is running the expected command.
    """
    if pid is None:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False
        )
        # Check if the process exists and the command name is in the output
        return result.returncode == 0 and expected_name in result.stdout
    except Exception:
        return False


def get_log_tail(log_path: Path, lines: int = 5) -> str:
    """Gets the last N lines of a log file."""
    if not log_path.exists():
        return f"Log file not found:\n{log_path.name}"
    try:
        with log_path.open("r") as f:
            # Use a deque for an efficient way to get the last lines
            return "".join(deque(f, lines))
    except Exception as e:
        return f"Could not read log file:\n{e}"


class HealthChecker:
    """A service to monitor the health of the pipeline components."""

    def __init__(self):
        self.shutdown_requested = False
        self.current_state = HealthCheckerState.CHECKING_HEALTH
        self.next_run_time = 0
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, _signum, _frame):
        if not self.shutdown_requested:
            logger.info("Shutdown signal received.")
            self.shutdown_requested = True

    def _generate_report(self, health_data: dict):
        """Generates a PNG image report of the system status using Matplotlib."""
        logger.info("Generating health report PNG...")
        num_services = len(health_data)
        fig, axes = plt.subplots(
            num_services, 2, figsize=(12, 2 * num_services), gridspec_kw={"width_ratios": [1, 4]}
        )
        fig.suptitle("Phorest Pipeline Health Status", fontsize=16, y=0.95)

        color_map = {"green": "green", "yellow": "gold", "red": "red", "grey": "grey"}

        for i, (service, data) in enumerate(health_data.items()):
            # Ensure axes is always a 2D array, even with one service
            ax_indicator = axes[i, 0] if num_services > 1 else axes[0]
            ax_text = axes[i, 1] if num_services > 1 else axes[1]

            # --- Traffic Light Column ---
            ax_indicator.set_xlim(0, 1)
            ax_indicator.set_ylim(0, 1)
            ax_indicator.add_patch(
                plt.Circle((0.5, 0.5), 0.4, color=color_map.get(data["color"], "grey"))
            )
            ax_indicator.axis("off")
            ax_indicator.set_aspect("equal", "box")

            # --- Status Text Column ---
            ax_text.axis("off")
            status_text = (
                f"Service: {service}\n"
                f"Status: {data['status'].upper()}\n"
                f"PID: {data.get('pid', 'N/A')}\n"
                f"Last Heartbeat: {data.get('last_heartbeat', 'N/A')}"
            )
            if data.get("log_tail"):
                status_text += f"\n\nLast Log Entries:\n{data['log_tail']}"

            ax_text.text(0, 0.5, status_text, va="center", ha="left", wrap=True, fontsize=10)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        report_path = Path(RESULTS_DIR, REPORT_FILENAME)
        try:
            plt.savefig(report_path)
            logger.info(f"Health report saved to {report_path}")
        except Exception as e:
            logger.error(f"Failed to save health report: {e}")
        finally:
            plt.close(fig)

    def _perform_health_check(self):
        """The main logic for checking the status of all services."""
        status_path = Path(FLAG_DIR, STATUS_FILENAME)
        health_data = {}

        try:
            with lock_and_manage_file(status_path):
                with status_path.open("r") as f:
                    status_json = json.load(f)
        except Exception as e:
            logger.error(f"Could not load status file at {status_path}: {e}")
            return

        for service, config in SERVICE_CONFIG.items():
            data = status_json.get(service, {})
            pid = data.get("pid")
            heartbeat_str = data.get("last_heartbeat")
            status = data.get("status", "unknown")

            health_info = {"pid": pid, "last_heartbeat": heartbeat_str, "log_tail": None}

            if status == "stopped":
                health_info["status"] = "Stopped"
                health_info["color"] = "grey"
            elif not is_pid_active(pid, service):
                health_info["status"] = "Crashed"
                health_info["color"] = "red"
                health_info["log_tail"] = get_log_tail(Path(LOGS_DIR, config["log"]))
            elif heartbeat_str is None:
                health_info["status"] = "No Heartbeat"
                health_info["color"] = "yellow"
            else:
                now = datetime.datetime.now()
                last_heartbeat = datetime.datetime.fromisoformat(heartbeat_str)
                time_since_heartbeat = (now - last_heartbeat).total_seconds()
                allowed_time = config["interval"] * 1.5  # Allow a 50% buffer

                if time_since_heartbeat > allowed_time:
                    health_info["status"] = "Hung / Stale Heartbeat"
                    health_info["color"] = "yellow"
                    health_info["log_tail"] = get_log_tail(Path(LOGS_DIR, config["log"]))
                else:
                    health_info["status"] = "Running OK"
                    health_info["color"] = "green"

            health_data[service] = health_info
        return health_data

    def _perform_health_check_cycle(self):
        """State machin logic for the health checker."""

        if settings is None:
            logger.debug("Configuration error. Halting.")
            self.current_state = HealthCheckerState.FATAL_ERROR

        match self.current_state:
            case HealthCheckerState.IDLE:
                logger.debug("IDLE -> WAITING_TO_RUN")
                self.next_run_time = time.monotonic() + HEALTH_CHECK_INTERVAL
                logger.debug(f"Will wait for {HEALTH_CHECK_INTERVAL} seconds until next cycle...")
                self.current_state = HealthCheckerState.WAITING_TO_RUN

            case HealthCheckerState.WAITING_TO_RUN:
                now = time.monotonic()
                if now >= self.next_run_time:
                    logger.debug("WAITING_TO_RUN -> CHECKING_HEALTH")
                    self.current_state = HealthCheckerState.CHECKING_HEALTH
                else:
                    for _ in range(int(POLL_INTERVAL)):
                        if self.shutdown_requested:
                            return
                        time.sleep(1)

            case HealthCheckerState.CHECKING_HEALTH:
                logger.info("--- Starting Health Check Cycle ---")
                try:
                    health_data = self._perform_health_check()
                    if health_data:
                        self._generate_report(health_data)
                    logger.info("--- Health Check Cycle Finished ---")
                except Exception as e:
                    logger.error(f"Error during health check cycle: {e}")

                self.current_state = HealthCheckerState.IDLE

            case HealthCheckerState.FATAL_ERROR:
                logger.error("[FATAL ERROR] Shutting down health checker.")
                time.sleep(10)  # Prevent busy-looping in fatal state

    def run(self):
        """Main loop for the health checker process."""
        logger.info("--- Starting Health Checker ---")
        print("--- Starting Health Checker ---")

        if settings is None:
            logger.debug("Configuration error. Halting.")
            return

        if not ENABLE_HEALTH_CHECK:
            logger.info("Health checker is disabled in config. Exiting.")
            return

        try:
            while not self.shutdown_requested:
                self._perform_health_check_cycle()

                time.sleep(0.1)
        except Exception as e:
            logger.critical(f"UNEXPECTED ERROR in main loop: {e}", exc_info=True)
        finally:
            logger.info("--- Health Checker Stopped ---")
            print("--- Health Checker Stopped ---")


def run_health_check():
    """Main entry point to create and run a HealthChecker instance."""
    checker = HealthChecker()
    checker.run()
