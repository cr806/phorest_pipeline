# src/phorest_pipeline/tui/textual_main.py
import os
import signal
import subprocess
from pathlib import Path

# --- Textual Imports ---
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Markdown, RichLog, Static

from phorest_pipeline.shared.metadata_manager import (
    get_pipeline_status,
    initialise_status_file,
    update_service_status,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TUI_HELP = Path(Path(__file__).resolve().parent, "TUI_help.md")


# --- Helper functions for PID management ---
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
        "script": "phorest-generate-roi-manifest",
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
    {"menu": "Start Continuous Capture", "script": "phorest-continuous-capture", "type": "background"},
    {"menu": "Capture Single Image", "script": "phorest-single-capture", "type": "background"},
]


class Help(Screen):
    """The help screen for the application."""

    BINDINGS = [("escape,space,q,question_mark", "app.pop_screen", "Close")]

    def compose(self) -> ComposeResult:
        yield Markdown(TUI_HELP.read_text())


class ServiceControl(Static):
    """A widget to display and control a single background service."""

    # reactive() makes this attribute automatically update the UI when it changes
    is_running = reactive(False)

    def __init__(self, name: str, script_id: str) -> None:
        super().__init__()
        self.service_name = name
        self.script_id = script_id

    def compose(self) -> ComposeResult:
        """Create the child widgets for this control."""
        with Horizontal():
            yield Static(self.service_name, classes="service_label")
            yield Button("Start", id=f"start_{self.script_id}", variant="success")
            yield Button("Stop", id=f"stop_{self.script_id}", variant="error")

    def watch_is_running(self, is_running: bool) -> None:
        """Called when the 'is_running' reactive attribute changes."""
        # This is the core logic: disable/enable buttons based on the state
        self.query_one(f"#start_{self.script_id}", Button).disabled = is_running
        self.query_one(f"#stop_{self.script_id}", Button).disabled = not is_running


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
        for service, data in all_statuses.items():
            if data.get("status") == "running" and is_pid_active(data.get("pid"), service):
                active_processes.append({"name": service, "pid": data.get("pid")})

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
                for service, p in all_statuses.items()
                if p.get("status") == "running" and is_pid_active(p.get("pid"), service)
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
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("m", "manage", "Manage Processes"),
        ("h", "help", "Help"),
    ]

    def on_mount(self) -> None:
        """Set up a timer to refresh the status every few seconds."""
        self.refresh_status()
        self.set_interval(2, self.refresh_status)  # Refresh every 2 seconds

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header("Phorest Pipeline TUI")

        # Use a scrollable container for all the buttons
        with VerticalScroll():
            yield Static("Phorest data collection and processing services", classes="group_header")
            with Vertical(id="background_container"):
                for item in BACKGROUND_SCRIPTS:
                    yield ServiceControl(name=item["menu"], script_id=item["script"])

            yield Static("Phorest single-use scripts", classes="group_header")
            with Container(id="foreground_container"):
                for item in FOREGROUND_SCRIPTS:
                    yield Button(item["menu"], id=item["script"])

        yield Footer()

    def refresh_status(self) -> None:
        """Get the latest status and update the UI."""
        all_statuses = get_pipeline_status()
        for service_control in self.query(ServiceControl):
            status_data = all_statuses.get(service_control.script_id, {})
            is_running = status_data.get("status") == "running" and is_pid_active(
                status_data.get("pid"),
                service_control.script_id
            )
            service_control.is_running = is_running

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        button_id = str(event.button.id or "")

        # --- Handle Foreground Scripts ---
        fg_script_info = next((s for s in FOREGROUND_SCRIPTS if s["script"] == button_id), None)
        if fg_script_info:
            self.push_screen(CommandOutputScreen(fg_script_info["menu"], button_id))
            return

        # --- Handle Start/Stop Buttons for Background Services ---
        if button_id.startswith("start_"):
            command_id = button_id.replace("start_", "")
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
                self.bell()
            except Exception:
                pass  # Add error dialog in a real app
            self.refresh_status()

        elif button_id.startswith("stop_"):
            command_id = button_id.replace("stop_", "")
            all_statuses = get_pipeline_status()
            pid_to_kill = all_statuses.get(command_id, {}).get("pid")
            if pid_to_kill and is_pid_active(pid_to_kill, command_id):
                try:
                    os.kill(pid_to_kill, signal.SIGINT)
                    update_service_status(command_id, pid=None, status="stopped")
                    self.bell()
                except Exception:
                    pass  # Add error dialog
            self.refresh_status()

    def action_manage(self) -> None:
        """Action to show the process management screen."""
        self.push_screen(ManageProcessesScreen())

    def action_help(self) -> None:
        """Action to show the help screen."""
        self.push_screen(Help())


def main():
    """Main entry point for the application."""
    all_service_names = [s["script"] for s in BACKGROUND_SCRIPTS]
    initialise_status_file(all_service_names)
    app = PhorestTUI()
    app.run()


if __name__ == "__main__":
    main()
