## Raspberry Pi Installation Guide

This guide provides the minimal steps required to set up the Phorest Pipeline project on a fresh Raspberry Pi.

### 1. Update Your System

First, ensure your Raspberry Pi's package lists and installed packages are up to date.
```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Install Git and `uv`

You will need `git` to clone the repository and `uv` to manage the Python environment.
```bash
sudo apt-get install git -y
curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
```
After installing `uv`, you may need to restart your terminal or run `source $HOME/.cargo/env` for the `uv` command to be available.

### 3. Clone the Project

Clone the Phorest Pipeline repository from GitHub to your desired location (e.g., the home directory).
```bash
git clone <your-repository-url>
cd phorest-pipeline
```

### 4. Install Dependencies

Use `uv` to create a virtual environment and install all the required Python packages. This command reads the `pyproject.toml` and `uv.lock` files to create a consistent environment.
```bash
uv sync
```

### 5. Activate the Environment

To use the installed packages, you must activate the virtual environment for your current terminal session.
```bash
source .venv/bin/activate
```

### 6. Initial Configuration

Before running the application for the first time, you will need to:

* Copy any example configuration files (e.g., `Phorest_config.example.toml`) to their final names (e.g., `Phorest_config.toml`).
* Edit the `.toml` files in the `configs/` directory to match your specific hardware and experimental setup.

The system is now installed and ready for calibration and use.
