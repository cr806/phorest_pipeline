import curses
import subprocess
import sys
import os
import signal # Needed for sending signals
import time   # For pauses and simulating work

# --- Global Storage for Running Processes ---
# Stores a list of dictionaries, each representing a running background process.
# Each dictionary contains:
#   'name': The name of the script file.
#   'pid': The Process ID.
#   'process_obj': The actual subprocess.Popen object, allowing interaction (poll(), send_signal()).
#   'log_path': The path to the specific log file for this process instance.
running_processes = []

# --- Script Categories ---
# These scripts will run synchronously, and their output will be displayed in the TUI.
info_gathering_scripts = [
    "test/script_01_environment_setup.py",
    "test/script_02_database_information.py",
]

# These scripts will be launched in the background, and the TUI will continue running.
background_scripts = [
    "test/script_03_network_check.py",
    "test/script_04_config_template_generation.py",
    "test/script_05_user_guidance.py",
]

# Special menu item for process management
MANAGE_PROCESSES_OPTION = "Manage Running Processes"

# Combine all script options for the main menu, plus the management option.
all_scripts = info_gathering_scripts + background_scripts + [MANAGE_PROCESSES_OPTION]

# --- Create Dummy Placeholder Scripts for Testing ---
# These dummy scripts ensure that the TUI has executable files to work with,
# simulating real scripts. They also include basic SIGINT handling for testing.
for script_name in (info_gathering_scripts + background_scripts):
    if not os.path.exists(script_name):
        with open(script_name, "w") as f:
            f.write(f'import time\n')
            f.write(f'import sys\n')
            f.write(f'import os\n')
            f.write(f'import signal\n')
            f.write(f'\n')
            f.write(f'# Basic SIGINT (Ctrl+C) handler for graceful exit\n')
            f.write(f'def handler(signum, frame):\n')
            f.write(f'    print(f"[{os.getpid()}] {script_name} received SIGINT ({signum}). Exiting gracefully.", file=sys.stderr)\n')
            f.write(f'    sys.exit(0) # Exit cleanly after SIGINT\n')
            f.write(f'signal.signal(signal.SIGINT, handler)\n')
            f.write(f'\n')
            f.write(f'print(f"[{os.getpid()}] Starting {script_name}...")\n')

            if script_name in info_gathering_scripts:
                # Dummy content for info-gathering scripts
                f.write(f'print(f"--- Output for {script_name} ---\\n")\n')
                f.write(f'print(f"This is a simulated informational output for {script_name}.")\n')
                f.write(f'print(f"Line 2 of info: More details here...")\n')
                f.write(f'print(f"Remember to note down this value: XYZ123 (from PID {os.getpid()})")\n')
                f.write(f'time.sleep(1) # Simulate some work\n')
            else:
                # Dummy content for background scripts (long-running)
                f.write(f'print(f"[{os.getpid()}] {script_name} running in background. Will print heartbeat every 5s...", flush=True)\n')
                f.write(f'for i in range(1, 100):\n') # Loop for a long time to keep process alive
                f.write(f'    print(f"[{os.getpid()}] {script_name} heartbeat {i}/100", flush=True)\n')
                f.write(f'    time.sleep(5) # Simulate work, allows for longer running\n')
                f.write(f'print(f"[{os.getpid()}] {script_name} finished background task normally.")\n')

# --- Helper to generate unique log file names for background processes ---
def get_unique_log_filename(script_name, pid):
    log_dir = "test/script_logs"
    os.makedirs(log_dir, exist_ok=True) # Ensure the log directory exists
    base_name = os.path.basename(script_name).replace(".py", "") # Remove .py extension
    return os.path.join(log_dir, f"{base_name}_{pid}.log")

# --- Function to run a background script and store its PID and Popen object ---
def run_background_script(stdscr, script_name):
    """
    Launches the given Python script in the background, detaches it from the TUI,
    and stores its process information in the global running_processes list.
    """
    stdscr.clear()
    stdscr.addstr(0, 0, f"Attempting to launch '{script_name}' in background...")
    stdscr.refresh()
    curses.napms(500) # Small delay to show the "Launching..." message

    try:
        # Create a temporary log file name before knowing the actual PID
        temp_log_path = get_unique_log_filename(script_name, "temp")
        log_file = open(temp_log_path, "w") # Open for writing output

        # Use subprocess.Popen to launch the script
        # - [sys.executable, script_name]: Runs the script with the current Python interpreter.
        # - stdin=subprocess.DEVNULL: Prevents the background script from reading TUI input.
        # - stdout=log_file, stderr=subprocess.STDOUT: Redirects all output (stdout and stderr) to the log file.
        # - preexec_fn=os.setsid: CRITICAL for detachment. Makes the child process the leader of a new session,
        #   detaching it from the controlling terminal and the TUI's process group. This ensures it runs
        #   even if the TUI exits.
        process = subprocess.Popen(
            [sys.executable, script_name],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
            close_fds=True # Close inherited file descriptors for robustness
        )

        # After launching, we know the actual PID, so rename the log file to include it.
        actual_log_path = get_unique_log_filename(script_name, process.pid)
        log_file.close() # Close the original file handle before renaming
        os.rename(temp_log_path, actual_log_path)


        # Store the process's information in our global list
        running_processes.append({
            'name': script_name,
            'pid': process.pid,
            'process_obj': process,
            'log_path': actual_log_path
        })

        # Provide visual feedback to the user
        stdscr.clear()
        stdscr.addstr(0, 0, f"'{script_name}' launched in background (PID: {process.pid}).", curses.A_BOLD)
        stdscr.addstr(1, 0, f"Log: {actual_log_path}", curses.A_DIM)
        stdscr.addstr(3, 0, "Press any key to return to menu...")
        stdscr.refresh()
        stdscr.getch() # Wait for user acknowledgment
        return True # Indicate successful launch
    except Exception as e:
        # If launching fails, display an error and print to stderr for debugging outside TUI
        stdscr.clear()
        stdscr.addstr(0, 0, f"Failed to launch '{script_name}': {e}", curses.A_BOLD | curses.A_RED)
        stdscr.addstr(1, 0, "Press any key to continue...")
        stdscr.refresh()
        stdscr.getch()
        print(f"Error launching script '{script_name}': {e}", file=sys.stderr)
        return False # Indicate failed launch

# --- Main Menu Drawing Function ---
def draw_menu(stdscr, selected_row_idx):
    """Draws the main script selection menu on the curses screen."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    title = "Project Setup Scripts"
    stdscr.addstr(0, w // 2 - len(title) // 2, title, curses.A_BOLD)
    stdscr.addstr(2, 0, "Use UP/DOWN arrows to navigate, ENTER to select, Q to quit.")
    
    # Display information about current running processes (updates dynamically)
    active_count = len([p for p in running_processes if p['process_obj'].poll() is None])
    stdscr.addstr(3, 0, f"Running background processes: {active_count}", curses.A_DIM)
    stdscr.addstr(4, 0, "Scripts for information gathering are underlined.")

    y_offset = 6 # Start menu items from row 6 to make space for header info

    for idx, script_option in enumerate(all_scripts):
        x = w // 2 - 20
        y = y_offset + idx
        
        attrs = 0
        if script_option in info_gathering_scripts:
            attrs |= curses.A_UNDERLINE # Underline info scripts
            
        if idx == selected_row_idx:
            attrs |= curses.A_REVERSE # Highlight selected item
        
        stdscr.addstr(y, x, script_option, attrs)

    stdscr.refresh()

# --- Function to display captured output from info-gathering scripts ---
def display_script_output(stdscr, script_name):
    """
    Runs an information-gathering script, captures its output, and displays it in the TUI.
    Includes basic scrolling for long outputs.
    """
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    message = f"Running '{script_name}' and capturing output..."
    stdscr.addstr(0, w // 2 - len(message) // 2, message)
    stdscr.refresh()
    curses.napms(500) # Small delay to show "Running..." message

    try:
        # subprocess.run is used for synchronous execution and output capture
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True, # Captures stdout and stderr
            text=True,           # Decodes output as string (UTF-8 by default)
            check=True           # Raises CalledProcessError if script returns non-zero exit code
        )

        all_output_lines = []
        if result.stdout:
            all_output_lines.append(f"--- Output for '{script_name}' (STDOUT) ---")
            all_output_lines.extend(result.stdout.splitlines())
        if result.stderr:
            all_output_lines.append(f"\n--- Errors/Warnings for '{script_name}' (STDERR) ---")
            all_output_lines.extend(result.stderr.splitlines())

        current_scroll_pos = 0
        while True:
            stdscr.clear()
            
            # Display current viewable portion of the output
            start_line_idx = current_scroll_pos
            end_line_idx = min(len(all_output_lines), current_scroll_pos + h - 4) # Reserve 4 lines for header/footer

            for i in range(start_line_idx, end_line_idx):
                line = all_output_lines[i]
                display_line = line[:w-1] # Truncate line to fit screen width
                
                attrs = 0
                # Simple check to color lines from stderr red
                if result.stderr and line in result.stderr.splitlines():
                     attrs |= curses.A_RED
                stdscr.addstr(2 + (i - start_line_idx), 0, display_line, attrs)

            stdscr.addstr(0, 0, f"Output for '{script_name}'", curses.A_BOLD) # Header
            
            # Footer for navigation instructions and scroll indicators
            footer_message = "Use UP/DOWN for scroll, ENTER to return to menu"
            if len(all_output_lines) > (h - 4): # Only show scroll hints if content overflows
                if current_scroll_pos > 0:
                    stdscr.addstr(h - 2, 0, " ^ (More above) ^ ", curses.A_DIM)
                if current_scroll_pos + (h - 4) < len(all_output_lines):
                     stdscr.addstr(h - 2, w - len(" v (More below) v ") -1, " v (More below) v ", curses.A_DIM)
            
            stdscr.addstr(h - 1, w // 2 - len(footer_message) // 2, footer_message, curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch() # Wait for user input

            if key == curses.KEY_UP:
                current_scroll_pos = max(0, current_scroll_pos - 1)
            elif key == curses.KEY_DOWN:
                max_scroll = max(0, len(all_output_lines) - (h - 4))
                current_scroll_pos = min(max_scroll, current_scroll_pos + 1)
            elif key == curses.KEY_ENTER or key in [10, 13]: # Enter key
                break # Exit output display and return to main menu

    except subprocess.CalledProcessError as e:
        # Handles cases where the script itself returns an error code
        stdscr.clear()
        stdscr.addstr(0, 0, f"Error running script '{script_name}':", curses.A_BOLD | curses.A_RED)
        stdscr.addstr(1, 0, f"Command: {e.cmd}")
        stdscr.addstr(2, 0, f"Return Code: {e.returncode}")
        
        y_offset = 4
        if e.stdout:
            stdscr.addstr(y_offset, 0, "--- Script STDOUT ---", curses.A_BOLD)
            y_offset += 1
            for line in e.stdout.splitlines():
                if y_offset < h - 4: stdscr.addstr(y_offset, 0, line); y_offset += 1
                else: break
        if e.stderr:
            if y_offset < h - 4: stdscr.addstr(y_offset, 0, "--- Script STDERR ---", curses.A_BOLD | curses.A_RED); y_offset += 1
            for line in e.stderr.splitlines():
                if y_offset < h - 4: stdscr.addstr(y_offset, 0, line, curses.A_RED); y_offset += 1
                else: break
        
        footer_message = "Press any key to return to menu..."
        stdscr.addstr(h - 2, w // 2 - len(footer_message) // 2, footer_message, curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()

    except Exception as e:
        # Catches any other unexpected errors during script execution
        stdscr.clear()
        stdscr.addstr(0, 0, f"An unexpected error occurred: {e}", curses.A_BOLD | curses.A_RED)
        stdscr.addstr(2, 0, "Press any key to return to menu...")
        stdscr.refresh()
        stdscr.getch()

# --- New Function to Manage Running Processes ---
def manage_processes_screen(stdscr):
    global running_processes # Declare global to modify the list (e.g., remove exited processes)

    current_row_idx = 0 # Keeps track of the currently selected process in this screen
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        title = "Manage Running Processes"
        stdscr.addstr(0, w // 2 - len(title) // 2, title, curses.A_BOLD)
        stdscr.addstr(2, 0, "Use UP/DOWN to navigate, ENTER to select/manage, R: Refresh, C: Clean Up, B: Back.")
        stdscr.addstr(3, 0, "Select a process then press ENTER for options.")

        # Prepare list of processes for display
        display_processes = []
        # Temporarily store active process indices for current_row_idx adjustment
        # It's better to just manage 'running_processes' directly as it's modified.
        
        if not running_processes:
            stdscr.addstr(5, 0, "No background scripts currently tracked.", curses.A_DIM)
        else:
            # Loop through tracked processes and format their display string
            for idx, p_info in enumerate(running_processes):
                pid = p_info['pid']
                name = p_info['name']
                # Check current status using .poll()
                return_code = p_info['process_obj'].poll()
                if return_code is None:
                    status = "RUNNING"
                else:
                    status = f"EXITED ({return_code})"
                
                display_str = f"PID: {pid:<6} | Status: {status:<12} | Script: {name}"
                display_processes.append(display_str)

            # Display the processes list
            for idx, proc_str in enumerate(display_processes):
                y = 5 + idx # Start displaying from row 5
                attrs = 0
                if idx == current_row_idx:
                    attrs |= curses.A_REVERSE # Highlight selected item
                
                stdscr.addstr(y, 0, proc_str[:w-1], attrs) # Truncate to fit screen width

        stdscr.refresh()

        key = stdscr.getch() # Wait for user input

        if key == curses.KEY_UP:
            current_row_idx = max(0, current_row_idx - 1)
        elif key == curses.KEY_DOWN:
            current_row_idx = min(len(display_processes) - 1, current_row_idx + 1)
        elif key == ord('r') or key == ord('R'): # Refresh status
            # Simply re-entering the loop will cause statuses to be re-polled and display updated
            pass
        elif key == ord('c') or key == ord('C'): # Clean up completed processes from the list
            # Filter running_processes to only keep those that are still active
            running_processes[:] = [p for p in running_processes if p['process_obj'].poll() is None]
            # Adjust current_row_idx if the list size changed
            current_row_idx = min(current_row_idx, len(running_processes) - 1 if running_processes else 0)
        elif key == curses.KEY_ENTER or key in [10, 13]: # User selected a process for action
            if running_processes: # Check if there are processes to select
                selected_proc_info = running_processes[current_row_idx] # Get the actual process info dict
                
                # --- Sub-menu for managing the selected process ---
                stdscr.clear()
                stdscr.addstr(0, 0, f"Manage '{selected_proc_info['name']}' (PID: {selected_proc_info['pid']})", curses.A_BOLD)
                
                # Display current status of the selected process
                current_status = "RUNNING" if selected_proc_info['process_obj'].poll() is None else f"EXITED ({selected_proc_info['process_obj'].poll()})"
                stdscr.addstr(2, 0, f"Current Status: {current_status}", curses.A_DIM)
                
                stdscr.addstr(4, 0, "S: Stop (SIGINT), L: View Log, B: Back to process list")
                stdscr.refresh()
                
                sub_key = stdscr.getch() # Wait for sub-menu action

                if sub_key == ord('s') or sub_key == ord('S'): # Stop process (SIGINT)
                    if selected_proc_info['process_obj'].poll() is None: # Only try to stop if running
                        try:
                            stdscr.addstr(6, 0, f"Sending SIGINT to {selected_proc_info['name']}...", curses.A_YELLOW)
                            stdscr.refresh()
                            selected_proc_info['process_obj'].send_signal(signal.SIGINT)
                            
                            # Give it a short time to terminate gracefully
                            try:
                                selected_proc_info['process_obj'].wait(timeout=5)
                                stdscr.addstr(7, 0, f"'{selected_proc_info['name']}' terminated successfully.", curses.A_GREEN)
                            except subprocess.TimeoutExpired:
                                stdscr.addstr(7, 0, f"'{selected_proc_info['name']}' did not terminate gracefully after SIGINT.", curses.A_RED)
                                stdscr.addstr(8, 0, "You might need to send SIGTERM/SIGKILL if it's unresponsive.", curses.A_RED)
                        except ProcessLookupError: # Process might have just died unexpectedly
                            stdscr.addstr(7, 0, "Process already terminated.", curses.A_YELLOW)
                        except Exception as e:
                            stdscr.addstr(7, 0, f"Error sending signal: {e}", curses.A_RED)
                    else:
                        stdscr.addstr(6, 0, "Process is not running, cannot send SIGINT.", curses.A_YELLOW)
                    
                    stdscr.addstr(h-2, 0, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch() # Wait for user to acknowledge action result
                
                elif sub_key == ord('l') or sub_key == ord('L'): # View Log file
                    log_path = selected_proc_info['log_path']
                    if os.path.exists(log_path):
                        try:
                            with open(log_path, 'r') as f:
                                log_content = f.read()
                            
                            log_lines = log_content.splitlines()
                            log_scroll_pos = 0
                            while True: # Loop for log viewing with scrolling
                                stdscr.clear()
                                stdscr.addstr(0, 0, f"Log for '{selected_proc_info['name']}' (PID: {selected_proc_info['pid']})", curses.A_BOLD)
                                stdscr.addstr(1, 0, f"File: {log_path}", curses.A_DIM)

                                start_line_idx = log_scroll_pos
                                end_line_idx = min(len(log_lines), log_scroll_pos + h - 4)
                                for i in range(start_line_idx, end_line_idx):
                                    stdscr.addstr(3 + (i - start_line_idx), 0, log_lines[i][:w-1]) # Truncate line

                                footer_message = "Use UP/DOWN for scroll, ENTER to return to process menu"
                                if len(log_lines) > (h - 4):
                                    if log_scroll_pos > 0 and log_scroll_pos + (h - 4) < len(log_lines):
                                        stdscr.addstr(h - 2, 0, " ^ (More above) ^ ", curses.A_DIM)
                                        stdscr.addstr(h - 2, w - len(" v (More below) v ") -1, " v (More below) v ", curses.A_DIM)
                                    elif log_scroll_pos > 0:
                                        stdscr.addstr(h - 2, 0, " ^ (More above) ^ ", curses.A_DIM)
                                    elif log_scroll_pos + (h - 4) < len(log_lines):
                                        stdscr.addstr(h - 2, w - len(" v (More below) v ") -1, " v (More below) v ", curses.A_DIM)
                                stdscr.addstr(h - 1, w // 2 - len(footer_message) // 2, footer_message, curses.A_BOLD)
                                stdscr.refresh()
                                log_key = stdscr.getch()
                                if log_key == curses.KEY_UP:
                                    log_scroll_pos = max(0, log_scroll_pos - 1)
                                elif log_key == curses.KEY_DOWN:
                                    max_log_scroll = max(0, len(log_lines) - (h - 4))
                                    log_scroll_pos = min(max_log_scroll, log_scroll_pos + 1)
                                elif log_key == curses.KEY_ENTER or log_key in [10, 13]:
                                    break # Exit log viewer
                        except Exception as e:
                            stdscr.addstr(h-2, 0, f"Error reading log: {e}", curses.A_RED)
                            stdscr.addstr(h-1, 0, "Press any key to continue...")
                            stdscr.refresh()
                            stdscr.getch()
                    else:
                        stdscr.addstr(h-2, 0, "Log file not found or already deleted.", curses.A_YELLOW)
                        stdscr.addstr(h-1, 0, "Press any key to continue...")
                        stdscr.refresh()
                        stdscr.getch()
                
                # After any sub-action, loop for the manage_processes_screen continues.
                # 'B' will exit this inner loop.
            else: # If user pressed ENTER but there are no processes to select
                stdscr.addstr(h - 2, 0, "No processes to manage.", curses.A_YELLOW)
                stdscr.addstr(h - 1, 0, "Press any key to continue...")
                stdscr.refresh()
                stdscr.getch()

        elif key == ord('b') or key == ord('B'): # Back to main menu from manage screen
            break # Exit this management screen's loop

# --- Main TUI Application Loop ---
def main(stdscr):
    """Main function for the curses TUI application."""
    # Basic curses configuration
    curses.curs_set(0)  # Hide cursor
    curses.noecho()     # Do not echo keypresses to the screen
    curses.cbreak()     # React to keypresses instantly (no need for Enter key)
    stdscr.keypad(True) # Enable special keys like arrow keys

    current_row_idx = 0 # Index of the currently selected menu item

    while True:
        draw_menu(stdscr, current_row_idx) # Redraw the main menu

        key = stdscr.getch() # Get user input

        if key == curses.KEY_UP:
            current_row_idx = max(0, current_row_idx - 1)
        elif key == curses.KEY_DOWN:
            current_row_idx = min(len(all_scripts) - 1, current_row_idx + 1)
        elif key == curses.KEY_ENTER or key in [10, 13]: # Enter key (10 and 13 are common ASCII for Enter)
            selected_option = all_scripts[current_row_idx] # Get the selected menu item

            if selected_option == MANAGE_PROCESSES_OPTION:
                manage_processes_screen(stdscr) # Navigate to the process management screen
            elif selected_option in info_gathering_scripts:
                display_script_output(stdscr, selected_option) # Run and display output synchronously
            elif selected_option in background_scripts:
                # Launch background script asynchronously, TUI continues
                stdscr.clear()
                stdscr.addstr(0, 0, f"Launching '{selected_option}' in the background...")
                stdscr.refresh()
                curses.napms(1000) # Short delay for visual feedback

                if run_background_script(stdscr, selected_option): # Call the background launcher
                    # run_background_script already handles success/failure messages
                    pass # The background script function handles the feedback, loop continues.
                # Else, loop continues.
            
        elif key == ord('q') or key == ord('Q'): # Quit option
            # Check for running processes before quitting
            active_count = len([p for p in running_processes if p['process_obj'].poll() is None])
            if active_count > 0:
                # Warn user if background processes are still running
                stdscr.clear()
                stdscr.addstr(0, 0, f"WARNING: {active_count} background processes are still running!", curses.A_BOLD | curses.A_YELLOW)
                stdscr.addstr(2, 0, "Quitting TUI will NOT stop them. Manage them via 'Manage Processes' or manually.")
                stdscr.addstr(4, 0, "Press 'Q' again to force quit, or any other key to go back.")
                stdscr.refresh()
                second_key = stdscr.getch() # Wait for confirmation
                if second_key == ord('q') or second_key == ord('Q'):
                    return # User confirmed, exit TUI
                # Else, loop continues, redraws main menu (user implicitly chose to go back)
            else:
                return # No active processes, exit TUI immediately

# --- Entry point for the TUI application ---
if __name__ == '__main__':
    # curses.wrapper handles initialization and proper cleanup of the terminal
    # even if errors occur.
    curses.wrapper(main)