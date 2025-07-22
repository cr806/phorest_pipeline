# src/phorest_pipeline/tui/main.py
import curses
import os
import signal
import subprocess
import sys
from pathlib import Path

from phorest_pipeline.shared.config import FLAG_DIR
from phorest_pipeline.shared.metadata_manager import initialise_status_file

# --- Configuration for PID File ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PID_FILE = Path(PROJECT_ROOT, "flags", "background_pids.txt")  # File to store script_name,pid
PID_FILE.parent.mkdir(parents=True, exist_ok=True)
if not PID_FILE.exists():
    PID_FILE.touch()

# Define minimum dimensions for the TUI window
MIN_HEIGHT = 23
MIN_WIDTH = 80

# --- Script Categories ---
FOREGROUND_SCRIPTS = [
    {"menu": "Check USB Storage", "script": "phorest-check-storage"},
    {"menu": "Find Thermocouple Serial Numbers", "script": "phorest-find-thermocouples"},
    {"menu": "Find Camera Index", "script": "phorest-find-camera"},
    {"menu": "Locate Gratings in Image", "script": "phorest-generate-roi-manifest"},
    {"menu": "\t\t( Check ROI listing )", "script": "phorest-check-roi"},
]

BACKGROUND_SCRIPTS = [
    {"menu": "\t\t( Start Periodic Image Collection Process )", "script": "phorest-collector"},
    {"menu": "\t\t( Start Image Analysis Process )", "script": "phorest-processor"},
    {"menu": "\t\t( Start Data Plotting Process )", "script": "phorest-communicator"},
    {"menu": "\t\t( Start Image Compression Process )", "script": "phorest-compressor"},
    {"menu": "\t\t( Start File Backup Process )", "script": "phorest-backup"},
    {"menu": "\t\t( Start Sync to remote direcory Process )", "script": "phorest-syncer"},
    {"menu": "Start Continuous Image Capture", "script": "phorest-continuous-capture"},
]


# --- Interactive Function to Check and Manage Running Background Scripts ---
def check_running_background_scripts_status(stdscr):
    """
    Loads PIDs from the file, checks their status using 'ps',
    and presents an interactive list to manage them.
    Allows sending SIGINT to selected processes.
    """
    current_selected_row = 0
    h, w = stdscr.getmaxyx()

    while True:  # Loop for the interactive status screen
        stdscr.clear()
        stdscr.addstr(
            0,
            w // 2 - len("Manage Background Scripts") // 2,
            "Manage Background Scripts",
            curses.A_BOLD,
        )
        stdscr.addstr(
            2,
            0,
            "Use UP/DOWN to navigate, ENTER to refresh, 'K' to send SIGINT, 'Q' to return to menu.",
        )

        cleanup_pid_file()  # Always clean the file before displaying and interacting
        tracked_pids = get_tracked_pids()  # Get the now cleaned list
        active_processes_to_display = tracked_pids

        # # Filter for truly active processes to display for interaction
        # active_processes_to_display = []
        # for entry in tracked_pids:
        #     cmd = is_pid_active(entry["pid"])
        #     if cmd and ("python3" in cmd) and (f"{entry['name']}" in cmd):
        #         active_processes_to_display.append(entry)

        results_lines = []
        if not active_processes_to_display:
            results_lines.append("No active background scripts currently tracked.")
        else:
            for entry in active_processes_to_display:
                status_line = (
                    f"Script: {entry['name']:<30} | PID: {entry['pid']:<6} | Status: ACTIVE"
                )
                results_lines.append(status_line)

        # Ensure current_selected_row is within bounds if the list changed
        if len(active_processes_to_display) == 0:
            current_selected_row = 0
        else:
            current_selected_row = min(current_selected_row, len(active_processes_to_display) - 1)
            current_selected_row = max(
                0, current_selected_row
            )  # Prevent negative if list becomes empty

        # Display results with scrolling
        start_line_idx = 0  # This view always starts from the top if content is short
        if len(results_lines) > (h - 6):  # if results overflow, allow scrolling
            start_line_idx = max(0, current_selected_row - (h - 6) // 2)  # Center selected item
            if start_line_idx + (h - 6) > len(results_lines):
                start_line_idx = max(0, len(results_lines) - (h - 6))  # Adjust if near end

        for i in range(start_line_idx, min(len(results_lines), start_line_idx + h - 6)):
            line_to_display = results_lines[i]
            attrs = curses.color_pair(3)  # Green for active processes

            # Highlight the currently selected row
            if (
                i == current_selected_row and active_processes_to_display
            ):  # Only highlight if there are items
                attrs |= curses.A_REVERSE  # Reverse video for selected item

            stdscr.addstr(4 + (i - start_line_idx), 0, line_to_display[: w - 1], attrs)

        # Footer for navigation
        footer_message = (
            "Use UP/DOWN to navigate, ENTER to refresh, 'K' to send SIGINT, 'Q' to return to menu."
        )
        stdscr.addstr(h - 1, w // 2 - len(footer_message) // 2, footer_message, curses.A_BOLD)
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_selected_row = max(0, current_selected_row - 1)
        elif key == curses.KEY_DOWN:
            current_selected_row = min(
                len(active_processes_to_display) - 1, current_selected_row + 1
            )
        elif key == ord("k") or key == ord("K"):
            if active_processes_to_display:
                selected_process = active_processes_to_display[current_selected_row]
                issue_sigint(stdscr, selected_process["pid"], selected_process["name"])
                # After sending SIGINT, the loop will naturally redraw,
                # which will call cleanup_pid_file and update the list.
            else:
                stdscr.addstr(
                    h - 3,
                    0,
                    "No script selected or no active scripts to kill.",
                    curses.color_pair(2) | curses.A_BOLD,
                )
                stdscr.refresh()
                curses.napms(1000)  # Show message briefly
        elif key == curses.KEY_ENTER or key in [10, 13]:  # Refresh list
            # The loop naturally refreshes, but this gives an explicit "refresh"
            pass
        elif key == ord("q") or key == ord("Q"):
            break  # Exit this management screen


def start_all_background_scripts(stdscr):
    scripts_to_start = [
        "phorest-collector",
        "phorest-processor",
        "phorest-communicator",
        "phorest-compressor",
        "phorest-backup",
        "phorest-syncer",
    ]
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    message = "Starting all data collection, analysis, and backup scripts..."
    stdscr.addstr(0, w // 2 - len(message) // 2, message)
    stdscr.refresh()
    curses.napms(500)

    for command_name in scripts_to_start:
        run_background_script_detached(stdscr, command_name, ask_for_enter=False)
        curses.napms(1000)


def stop_all_background_scripts(stdscr):
    tracked_pids = get_tracked_pids()

    stdscr.clear()
    h, w = stdscr.getmaxyx()

    message = "Stopping all data collection, analysis, and backup scripts..."
    stdscr.addstr(0, w // 2 - len(message) // 2, message)
    stdscr.refresh()
    curses.napms(500)

    # Filter for truly active processes to display for interaction
    active_processes_to_stop = []
    for entry in tracked_pids:
        cmd = is_pid_active(entry["pid"])
        if cmd and ("python3" in cmd) and (f"{entry['name']}" in cmd):
            active_processes_to_stop.append(entry)

    stdscr.clear()
    stdscr.refresh()
    for process in active_processes_to_stop:
        issue_sigint(stdscr, process["pid"], process["name"], ask_for_enter=False)
        curses.napms(500)


multiple_action_functions = [
    {"menu": "START All processes for Data collection", "script": start_all_background_scripts},
    {"menu": "STOP All Data collection processes", "script": stop_all_background_scripts},
    {
        "menu": "MANAGE Running processes separately",
        "script": check_running_background_scripts_status,
    },
]

all_scripts = multiple_action_functions + BACKGROUND_SCRIPTS + FOREGROUND_SCRIPTS


# --- Helper functions for PID file management ---
def get_tracked_pids():
    """Reads the PID file and returns a list of (script_name, pid) dictionaries."""
    tracked_pids = []
    if PID_FILE.exists():
        with PID_FILE.open("r") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(",")
                    if len(parts) == 3:
                        try:
                            script_name = parts[0]
                            pid = int(parts[1])
                            status = parts[2].strip()
                            tracked_pids.append(
                                {
                                    "name": script_name,
                                    "pid": pid,
                                    "status": status,
                                }
                            )
                        except ValueError:
                            # Skip malformed lines
                            continue
    return tracked_pids


def add_pid_to_file(command_name, pid):
    """Appends a new script_name,pid entry to the PID file."""
    with PID_FILE.open("a") as f:
        f.write(f"{command_name},{pid},ACTIVE\n")


def is_pid_active(pid):
    """
    Checks if a given PID corresponds to an active process using 'ps -p PID -o command='.
    Returns the command string if active, None otherwise.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            return None  # PID does not exist or process is gone

        command_output = result.stdout.strip()
        if command_output:
            return command_output
        else:
            return None
    except Exception as e:
        print(f"Error checking PID {pid} with ps: {e}", file=sys.stderr)
        return None


def is_script_already_running(command_name):
    """
    Checks if an instance of the given script_name is already running
    by looking up tracked PIDs and verifying them with 'ps'.
    Does NOT modify the PID file; it only reads.
    Returns the PID if found, None otherwise.
    """
    tracked_pids = get_tracked_pids()  # Read all PIDs from the file

    for entry in tracked_pids:
        # Only check PIDs for the *specific* script we care about right now
        if entry["name"] == command_name:
            cmd = is_pid_active(entry["pid"])
            if cmd and command_name in cmd:
                return entry["pid"]  # Found an active instance
    return None  # No active instance found for this script


def cleanup_pid_file():
    """
    Reads the PID file, checks all PIDs for active processes,
    and rewrites the file with only the active, matching PIDs.
    This is an explicit cleanup step.
    """
    tracked_pids = get_tracked_pids()
    updated_pids_list = []

    for entry in tracked_pids:
        cmd = is_pid_active(entry["pid"])
        if cmd:
            # Check if the PID is still running the expected script
            if ("python3" in cmd) and (f"{entry['name']}" in cmd):
                updated_pids_list.append(entry)  # Keep this active entry
        else:
            updated_pids_list.append(
                {
                    "name": entry["name"],
                    "pid": entry["pid"],
                    "status": "DEAD",
                }
            )
    # Rewrite the PID file with only the valid, active entries
    with PID_FILE.open("w") as f:
        for entry in updated_pids_list:
            if entry["status"] == "ACTIVE":
                f.write(f"{entry['name']},{entry['pid']},{entry['status']}\n")


def refresh_pid_file():
    """
    Reads the PID file, checks all PIDs for active processes,
    and rewrites the file with only the active, matching PIDs.
    This is an explicit cleanup step.
    """
    tracked_pids = get_tracked_pids()
    updated_pids_list = []

    for entry in tracked_pids:
        cmd = is_pid_active(entry["pid"])
        if cmd:
            # Check if the PID is still running the expected script
            if ("python3" in cmd) and (f"{entry['name']}" in cmd):
                updated_pids_list.append(entry)  # Keep this active entry
        else:
            updated_pids_list.append(
                {
                    "name": entry["name"],
                    "pid": entry["pid"],
                    "status": "DEAD",
                }
            )
    # Rewrite the PID file with only the valid, active entries
    with PID_FILE.open("w") as f:
        for entry in updated_pids_list:
            f.write(f"{entry['name']},{entry['pid']},{entry['status']}\n")


# --- Main Menu Drawing Function ---
def draw_menu(stdscr, selected_row_idx):
    """Draws the main script selection menu on the curses screen."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    title = "Project Setup Scripts"
    stdscr.addstr(0, w // 2 - len(title) // 2, title, curses.A_BOLD)
    stdscr.addstr(2, 0, "Use UP/DOWN arrows to navigate, ENTER to select, Q to quit.")

    # Dynamically count active background processes for display.
    active_count = 0
    dead_count = 0
    refresh_pid_file()  # Ensure file is clean before counting for display
    for entry in get_tracked_pids():
        cmd = is_pid_active(entry["pid"])
        if cmd and ("python3" in cmd) and (f"{entry['name']}" in cmd):
            active_count += 1
        else:
            dead_count += 1
    stdscr.addstr(
        3, 0, f"Currently tracked ACTIVE background processes: {active_count}", curses.A_DIM
    )
    stdscr.addstr(4, 0, f"Currently tracked DEAD background processes: {dead_count}", curses.A_DIM)
    stdscr.addstr(5, 0, "Scripts for information gathering are underlined.")

    y_offset = 7

    for idx, script_option in enumerate(all_scripts):
        x = w // 2 - 20 // 2
        y = y_offset + idx

        attrs = 0
        # if script_option in FOREGROUND_SCRIPTS:
        #     attrs |= curses.A_UNDERLINE

        if idx == selected_row_idx:
            attrs |= curses.A_REVERSE

        stdscr.addstr(y, x, script_option["menu"], attrs)

    stdscr.refresh()


# --- Function to run a background script (simplified) ---
def run_background_script_detached(stdscr, command_name, ask_for_enter=True):
    """
    Launches the given Python script in the background, detaches it,
    and appends its PID to a text file. Includes single instance check.
    """
    existing_pid = is_script_already_running(command_name)
    if existing_pid:
        stdscr.clear()
        stdscr.addstr(
            0,
            0,
            f"Error: '{command_name}' is already running with PID {existing_pid}.",
            curses.color_pair(1) | curses.A_BOLD,
        )
        stdscr.addstr(2, 0, "Please stop the existing instance or choose another script.")
        stdscr.addstr(4, 0, "Press any key to return to menu...")
        stdscr.refresh()
        stdscr.getch()
        return False

    stdscr.clear()
    stdscr.addstr(0, 0, f"Attempting to launch '{command_name}' in background...")
    stdscr.refresh()
    curses.napms(500)

    try:
        process = subprocess.Popen(
            [command_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            close_fds=True,
            cwd=str(PROJECT_ROOT),  # Set the working directory to the project root
        )

        add_pid_to_file(command_name, process.pid)

        stdscr.clear()
        stdscr.addstr(
            0, 0, f"'{command_name}' launched in background (PID: {process.pid}).", curses.A_BOLD
        )
        if ask_for_enter:
            stdscr.addstr(2, 0, "Press any key to return to menu...")
            stdscr.refresh()
            stdscr.getch()
        else:
            stdscr.refresh()
        return True
    except Exception as e:
        stdscr.clear()
        stdscr.addstr(
            0, 0, f"Failed to launch '{command_name}': {e}", curses.color_pair(1) | curses.A_BOLD
        )
        stdscr.addstr(2, 0, "This may be because the project is not installed in editable mode.")
        stdscr.addstr(3, 0, "Try running: uv pip install -e .")
        stdscr.addstr(5, 0, "Press any key to continue...")
        stdscr.refresh()
        stdscr.getch()
        return False


# --- Function to display captured output from info-gathering scripts ---
def run_foreground_script(stdscr, command_name):
    """
    Runs an information-gathering script, captures its output, and displays it in the TUI.
    """
    ERROR_ATTRIBUTES = curses.color_pair(1) | curses.A_BOLD
    # WARNING_ATTRIBUTES = curses.color_pair(2) | curses.A_BOLD
    SUCCESS_ATTRIBUTES = curses.color_pair(3) | curses.A_BOLD
    # SUCCESS_ATTRIBUTES = 0  # No attributes for success

    stdscr.clear()
    h, w = stdscr.getmaxyx()

    message = f"Running '{command_name}' and capturing output..."
    stdscr.addstr(0, w // 2 - len(message) // 2, message)
    stdscr.refresh()
    curses.napms(500)

    try:
        result = subprocess.run(
            [command_name], capture_output=True, text=True, check=True, cwd=str(PROJECT_ROOT)
        )

        all_output_lines = []
        if result.stdout:
            all_output_lines.append(f"--- Output for '{command_name}' (STDOUT) ---")
            all_output_lines.extend(result.stdout.splitlines())
        if result.stderr:
            all_output_lines.append(f"\n--- Errors/Warnings for '{command_name}' (STDERR) ---")
            all_output_lines.extend(result.stderr.splitlines())

        current_scroll_pos = 0
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, f"Output for '{command_name}'", curses.A_BOLD)

            start_line_idx = current_scroll_pos
            end_line_idx = min(len(all_output_lines), current_scroll_pos + h - 4)

            for i in range(start_line_idx, end_line_idx):
                line = all_output_lines[i]
                display_line = line[: w - 1]

                attrs = 0
                if line in result.stderr.splitlines():
                    attrs |= ERROR_ATTRIBUTES
                elif line in result.stdout.splitlines():
                    attrs |= SUCCESS_ATTRIBUTES
                stdscr.addstr(2 + (i - start_line_idx), 0, display_line, attrs)

            footer_message = "Use UP/DOWN for scroll, ENTER to return to menu"
            if len(all_output_lines) > (h - 4):
                if current_scroll_pos > 0:
                    stdscr.addstr(h - 2, 0, " ^ (More above) ^ ", curses.A_DIM)
                if current_scroll_pos + (h - 4) < len(all_output_lines):
                    stdscr.addstr(
                        h - 2,
                        w - len(" v (More below) v ") - 1,
                        " v (More below) v ",
                        curses.A_DIM,
                    )

            stdscr.addstr(h - 1, w // 2 - len(footer_message) // 2, footer_message, curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch()

            if key == curses.KEY_UP:
                current_scroll_pos = max(0, current_scroll_pos - 1)
            elif key == curses.KEY_DOWN:
                max_scroll = max(0, len(all_output_lines) - (h - 4))
                current_scroll_pos = min(max_scroll, current_scroll_pos + 1)
            elif key == curses.KEY_ENTER or key in [10, 13]:
                break

    except subprocess.CalledProcessError as e:
        stdscr.clear()
        stdscr.addstr(0, 0, f"Error running script '{command_name}':", ERROR_ATTRIBUTES)
        stdscr.addstr(1, 0, f"Command: {e.cmd}")
        stdscr.addstr(2, 0, f"Return Code: {e.returncode}")

        y_offset = 4
        if e.stdout:
            stdscr.addstr(y_offset, 0, "--- Script STDOUT ---", curses.A_BOLD)
            y_offset += 1
            for line in e.stdout.splitlines():
                if y_offset < h - 4:
                    stdscr.addstr(y_offset, 0, line)
                    y_offset += 1
                else:
                    break
        if e.stderr:
            if y_offset < h - 4:
                stdscr.addstr(y_offset, 0, "--- Script STDERR ---", ERROR_ATTRIBUTES)
                y_offset += 1
            for line in e.stderr.splitlines():
                if y_offset < h - 4:
                    stdscr.addstr(y_offset, 0, line, ERROR_ATTRIBUTES)
                    y_offset += 1
                else:
                    break

        footer_message = "Press any key to return to menu..."
        stdscr.addstr(h - 2, w // 2 - len(footer_message) // 2, footer_message, curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()

    except Exception as e:
        stdscr.clear()
        stdscr.addstr(0, 0, f"An unexpected error occurred: {e}", ERROR_ATTRIBUTES)
        stdscr.addstr(2, 0, "Press any key to return to menu...")
        stdscr.refresh()
        stdscr.getch()


# --- Function to Issue SIGINT to a PID ---
def issue_sigint(stdscr, pid, script_name, ask_for_enter=True):
    """Attempts to send SIGINT to the given PID."""
    ERROR_ATTRIBUTES = curses.color_pair(1) | curses.A_BOLD
    SUCCESS_ATTRIBUTES = curses.color_pair(3) | curses.A_BOLD
    try:
        os.kill(pid, signal.SIGINT)
        message = f"Sent SIGINT to {script_name} (PID: {pid}). It should terminate gracefully."
        stdscr.addstr(0, 0, message, SUCCESS_ATTRIBUTES)  # Green for success
    except ProcessLookupError:
        message = f"Error: Process with PID {pid} not found (already terminated?)."
        stdscr.addstr(0, 0, message, ERROR_ATTRIBUTES)  # Red for error
    except Exception as e:
        message = f"Error sending SIGINT to {pid}: {e}"
        stdscr.addstr(0, 0, message, ERROR_ATTRIBUTES)  # Red for error

    if ask_for_enter:
        stdscr.addstr(2, 0, "Press any key to continue...")
        stdscr.refresh()
        stdscr.getch()
    else:
        stdscr.refresh()


# --- Main TUI Application Loop ---
def run_tui_app(stdscr):
    """Main function for the curses TUI application."""

    # --- Check Terminal Size ---
    h, w = stdscr.getmaxyx()
    if h < MIN_HEIGHT or w < MIN_WIDTH:
        # Return a dictionary with error info. The wrapper will handle teardown.
        return {
            "error": "size",
            "current_h": h,
            "current_w": w,
            "required_h": MIN_HEIGHT,
            "required_w": MIN_WIDTH,
        }

    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    # --- Initialize Colors ---
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(
            1, curses.COLOR_RED, curses.COLOR_BLACK
        )  # Pair 1: Red text on Black background (for errors)
        curses.init_pair(
            2, curses.COLOR_YELLOW, curses.COLOR_BLACK
        )  # Pair 2: Yellow text on Black background (for warnings)
        curses.init_pair(
            3, curses.COLOR_GREEN, curses.COLOR_BLACK
        )  # Pair 3: Green text on Black background (for active status)

    # ERROR_ATTRIBUTES = curses.color_pair(1) | curses.A_BOLD
    WARNING_ATTRIBUTES = curses.color_pair(2) | curses.A_BOLD

    cleanup_pid_file()

    current_row_idx = 0

    while True:
        draw_menu(stdscr, current_row_idx)

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_row_idx = max(0, current_row_idx - 1)
        elif key == curses.KEY_DOWN:
            current_row_idx = min(len(all_scripts) - 1, current_row_idx + 1)
        elif key == curses.KEY_ENTER or key in [10, 13]:
            selected_option = all_scripts[current_row_idx]

            if selected_option in multiple_action_functions:
                selected_option["script"](stdscr)
            elif selected_option in FOREGROUND_SCRIPTS:
                run_foreground_script(stdscr, selected_option["script"])
            elif selected_option in BACKGROUND_SCRIPTS:
                stdscr.clear()
                stdscr.addstr(
                    0, 0, f"Attempting to launch '{selected_option['script']}'...", curses.A_DIM
                )
                stdscr.refresh()
                curses.napms(500)

                run_background_script_detached(stdscr, selected_option["script"])

        elif key == ord("q") or key == ord("Q"):
            active_count = 0
            cleanup_pid_file()
            for entry in get_tracked_pids():
                cmd = is_pid_active(entry["pid"])
                if cmd and ("python3" in cmd) and (f"{entry['name']}" in cmd):
                    active_count += 1

            if active_count > 0:
                stdscr.clear()
                stdscr.addstr(
                    0,
                    0,
                    f"WARNING: {active_count} background processes are still running (tracked in {PID_FILE.as_posix()})!",
                    WARNING_ATTRIBUTES,
                )
                stdscr.addstr(
                    2, 0, "Quitting TUI will NOT stop them. Check 'ps aux' or stop manually."
                )
                stdscr.addstr(4, 0, "Press 'Q' again to force quit, or any other key to go back.")
                stdscr.refresh()
                second_key = stdscr.getch()
                if second_key == ord("q") or second_key == ord("Q"):
                    return
            else:
                return


def main():
    """The entry point for the phorest TUI application."""

    # Initialize the status file on startup
    all_service_names = [s["script"] for s in BACKGROUND_SCRIPTS]
    initialise_status_file(all_service_names, FLAG_DIR)

    # The curses.wrapper handles the curses setup and passes 'stdscr' to run_tui_app
    result = curses.wrapper(run_tui_app)

    if isinstance(result, dict) and result.get("error") == "size":
        print("Error: Terminal window is too small.", file=sys.stderr)
        print(
            f"       Current dimensions: {result['current_w']} width x {result['current_h']} height.",
            file=sys.stderr,
        )
        print(
            f"       Required minimum dimensions: {result['required_w']} width x {result['required_h']} height.",
            file=sys.stderr,
        )
        print("\nPlease resize your terminal window and run the script again.", file=sys.stderr)
        sys.exit(1)


# --- Entry point for the TUI application ---
if __name__ == "__main__":
    main()
