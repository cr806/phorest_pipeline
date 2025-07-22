# src/phorest_pipeline/tui/textual_main.py
import os
import signal
import subprocess
from pathlib import Path

# --- Textual Imports ---
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, RichLog, Static

from phorest_pipeline.shared.metadata_manager import (
    get_pipeline_status,
    initialise_status_file,
    update_service_status,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# --- Helper functions for PID management ---
def is_pid_active(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


# --- Data Definitions ---
FOREGROUND_SCRIPTS = [
    {"menu": "Check USB Storage", "script": "phorest-check-storage", "type": "foreground"},
    {"menu": "Initialise Directories", "script": "phorest-init-dirs", "type": "foreground"},
    {
        "menu": "Find Thermocouple Serials",
        "script": "phorest-find-thermocouples",
        "type": "foreground",
    },
    {"menu": "Find Camera Index", "script": "phorest-find-camera", "type": "foreground"},
    {
        "menu": "Locate Gratings in Image",
        "script": "phorest-prepare-analysis",
        "type": "foreground",
    },
    {"menu": "Check ROI listing", "script": "phorest-check-roi", "type": "foreground"},
]

BACKGROUND_SCRIPTS = [
    {"menu": "Start Collector", "script": "phorest-collector", "type": "background"},
    {"menu": "Start Processor", "script": "phorest-processor", "type": "background"},
    {"menu": "Start Communicator", "script": "phorest-communicator", "type": "background"},
    {"menu": "Start Compressor", "script": "phorest-compressor", "type": "background"},
    {"menu": "Start Backup", "script": "phorest-backup", "type": "background"},
    {"menu": "Start Syncer", "script": "phorest-syncer", "type": "background"},
    {"menu": "Start Health Check", "script": "phorest-health-check", "type": "background"},
    {
        "menu": "Start Continuous Capture",
        "script": "phorest-continuous-capture",
        "type": "background",
    },
]

# --- Screens ---
# Textual uses "Screens" to manage different views, like a main menu or a dialog box.


class CommandOutputScreen(Screen):
    """A screen to display the output of a foreground command."""

    def __init__(self, command_name: str, command_to_run: str):
        super().__init__()
        self.command_name = command_name
        self.command_to_run = command_to_run

    def compose(self) -> ComposeResult:
        yield Header(f"Output for {self.command_name}")
        yield RichLog(highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        """Called when the screen is first mounted. Runs the command."""
        log = self.query_one(RichLog)
        log.write(f"[yellow]Running command: {self.command_to_run}...[/yellow]\n")

        try:
            process = subprocess.Popen(
                [self.command_to_run],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
            )

            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    log.write(line)

            process.wait()
            if process.returncode == 0:
                log.write("\n[green]Command finished successfully.[/green]")
            else:
                log.write(f"\n[red]Command finished with error code {process.returncode}.[/red]")

        except Exception as e:
            log.write(f"\n[bold red]Failed to run command: {e}[/bold red]")

        log.write("\n[bold]Press any key to return to the main menu.[/bold]")

    def on_key(self) -> None:
        """Go back to the main app when any key is pressed."""
        self.app.pop_screen()


class ManageProcessesScreen(ModalScreen):
    """A screen for managing running background processes."""

    BINDINGS = [("q", "app.pop_screen", "Back to Menu")]

    def compose(self) -> ComposeResult:
        with Vertical(id="manage_dialog"):
            yield Header("Manage Background Scripts")
            yield DataTable(id="process_table")
            yield Button("Kill Selected Process", variant="error", id="kill_button")
            yield Footer()

    def on_mount(self) -> None:
        """Called when the screen is mounted. Populates the table."""
        table = self.query_one(DataTable)
        table.add_columns("Command", "PID", "Status")
        self.refresh_processes()

    def refresh_processes(self) -> None:
        """Clears and re-populates the process table."""
        table = self.query_one(DataTable)
        table.clear()

        all_statuses = get_pipeline_status()
        active_processes = []
        for name, data in all_statuses.items():
            if data.get("status") == "running" and is_pid_active(data.get("pid")):
                active_processes.append({"name": name, "pid": data.get("pid")})

        if not active_processes:
            table.add_row("[dim]No active processes found.[/dim]")
        else:
            for proc in active_processes:
                table.add_row(proc["name"], str(proc["pid"]), "[green]ACTIVE[/green]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles the kill button press."""
        if event.button.id == "kill_button":
            table = self.query_one(DataTable)

            all_statuses = get_pipeline_status()
            active_processes = [
                p
                for p in all_statuses.values()
                if p.get("status") == "running" and is_pid_active(p.get("pid"))
            ]
            if not active_processes or table.cursor_row < 0:
                self.app.bell()
                return

            row_data = table.get_row_at(table.cursor_row)
            command_id = row_data[0]
            pid_to_kill = int(row_data[1])

            try:
                os.kill(pid_to_kill, signal.SIGINT)
                update_service_status(command_id, pid=pid_to_kill, status="stopped")
                self.app.bell()  # Audible feedback
                self.refresh_processes()
            except Exception:
                # You could show a proper dialog here
                pass


# --- The Main App ---
class PhorestTUI(App):
    """The main Textual application for the Phorest Pipeline."""

    CSS_PATH = "tui_styles.css"
    BINDINGS = [("q", "quit", "Quit"), ("m", "manage", "Manage Processes")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header("Phorest Pipeline TUI")

        # Use a scrollable container for all the buttons
        with Container():
            with Vertical(id="foreground_container"):
                yield Static("Phorest single-use scripts", classes="group_header")
                for item in FOREGROUND_SCRIPTS:
                    yield Button(item["menu"], id=item["script"], classes="fg_button")

            with Vertical(id="background_container"):
                yield Static(
                    "Phorest data collection and processing services", classes="group_header"
                )
                for item in BACKGROUND_SCRIPTS:
                    yield Button(item["menu"], id=item["script"], classes="bg_button")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""

        command_id = event.button.id
        if not command_id:
            return

        # Find which script type was clicked
        script_info = next(
            (s for s in FOREGROUND_SCRIPTS + BACKGROUND_SCRIPTS if s["script"] == command_id), None
        )

        if not script_info:
            return

        if script_info["type"] == "foreground":
            # For foreground scripts, push a new screen to show the output
            self.push_screen(CommandOutputScreen(script_info["menu"], command_id))

        elif script_info["type"] == "background":
            # For background scripts, launch them and show a notification (or a brief dialog)
            try:
                process = subprocess.Popen(
                    [command_id],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                    cwd=str(PROJECT_ROOT),
                )
                update_service_status(command_id, pid=process.pid, status="running")
                self.bell()  # Simple feedback
            except Exception:
                # In a real app, you'd show a proper error dialog here
                pass

    def action_manage(self) -> None:
        """Action to show the process management screen."""
        self.push_screen(ManageProcessesScreen())


def main():
    """Main entry point for the application."""

    # Initialize the status file on startup
    all_service_names = [s["script"] for s in BACKGROUND_SCRIPTS]
    initialise_status_file(all_service_names)

    app = PhorestTUI()
    app.run()


if __name__ == "__main__":
    main()
