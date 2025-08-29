# Guide: Deploying a Python CLI Tool with UV

This guide explains the complete workflow for deploying the Phorest pipeline as a command-line tool from a Git repository using `uv`. It covers cloning the project, creating a reproducible virtual environment, and installing the tool for system-wide access.

---
### Step 1: Update and install pre-requisites

1. **Update Your System**:  
   * First, ensure your Raspberry Pi's package lists and installed packages are up to date.
       ```bash
       sudo apt-get update
       sudo apt-get upgrade -y
       ```

2. **Install Git and `uv`**:
   * You will need `git` to clone the repository and `uv` to manage the Python environment.
       ```bash
       sudo apt-get install git -y
       curl -LsSf https://astral.sh/uv/install.sh | sh
       ```

### Step 2: Clone the Project Repository

First, get a copy of the project's source code from its Git repository.

1.  **Clone the Repository**:
    * Open a terminal and run the `git clone` command, replacing the placeholder with your repository's URL.
        ```bash
        git clone <YOUR_REPOSITORY_URL>
        ```
2.  **Navigate into the Directory**:
    * Move into the newly created project folder.
        ```bash
        cd <YOUR_PROJECT_DIRECTORY>
        ```

---
### Step 3: Create and Activate the Virtual Environment

Next, create an isolated Python environment for the project's dependencies. This prevents conflicts with other Python projects on your system.

1.  **Create the Environment**:
    * Use `uv` to create a new virtual environment. This command is extremely fast and creates a standard `.venv` directory.
        ```bash
        uv venv
        ```
2.  **Activate the Environment**:
    * Activate the new environment to ensure subsequent commands use it.
        ```bash
        source .venv/bin/activate
        ```
    * Your shell prompt should now be prefixed with `(.venv)`.

---
### Step 4: Sync Dependencies from `uv.lock`

Install the project's exact dependencies using the `uv.lock` file. This ensures your environment is a perfect mirror of the one defined by the project, which is critical for reproducibility.

1.  **Run the Sync Command**:
    * The `uv sync` command installs all required packages and removes any that don't belong, guaranteeing a clean setup.
        ```bash
        uv sync
        ```

---
### Step 5: Install the Project as a Command-Line Tool

Finally, install the project's scripts (i.e. the `phorest` command) so they can be run from any directory on your machine without needing to activate the virtual environment each time.

1.  **Install the Tool**:
    * Note: Ensure that the repository is on the correct branch before installing
    * From the root of your project directory, run the `uv tool install` command. The example below includes an optional dependency group (`tui`), which you should adjust as needed.
        ```bash
        uv tool install ".[tui]"
        ```
    * **`.`**: This tells `uv` to install the project from the current directory.
    * **`[tui]`**: This specifies an optional dependency group defined in your `pyproject.toml`.

2.  **Verify the Installation**:
    * Check that the tool is listed by `uv`.
        ```bash
        uv tool list
        ```
    * Move to your home directory and test the command to ensure it's globally accessible.
        ```bash
        cd ~
        phorest --help
        ```

Your Python application is now correctly deployed as a command-line tool on your server.