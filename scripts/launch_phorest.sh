#!/usr/bin/env bash

# --- Phorest TUI Launcher ---
#
# This script provides a reliable way to start the Phorest TUI application.
# It automatically locates the project root and uses `uv run` to ensure the
# correct virtual environment is used.
#
# --- Installation for System-Wide Use ---
# To make the TUI runnable from anywhere by simply typing 'phorest',
# follow these steps:
#
# 1. Place this script in a permanent location within the project,
#    for example: /path/to/project/scripts/launch_phorest.sh
#
# 2. Make the script executable:
#    chmod +x /path/to/project/scripts/launch_phorest.sh
#
# 3. Create a symbolic link to it in /usr/local/bin:
#    sudo ln -s /path/to/project/scripts/launch_phorest.sh /usr/local/bin/phorest
#
# After this, you can run 'phorest' from any terminal.

# --- Find the Project Root ---
PROJECT_ROOT=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )
echo "Project root found at: $PROJECT_ROOT"

# --- Change to Project Directory ---
cd "$PROJECT_ROOT" || { echo "Error: Could not change to project directory."; exit 1; }

# --- Launch the TUI using uv run ---
echo "Launching Phorest TUI via 'uv run'..."
uv run phorest-tui-adv

echo "TUI closed. Exiting."