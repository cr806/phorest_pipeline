# Process Pipeline

A multi-process pipeline for data collection, processing, and communication using file flags.

## Setup

1. Clone repo.
2. `cd <repo>`

## Running

Open three separate terminals, and run:

- Terminal 1: `uv run run_collector.py`
- Terminal 2: `uv run run_processor.py`
- Terminal 3: `uv run run_communicator.py`

Note: On first running one of these commands uv will download project dependencies, set-up a virtual environment, activate the environment and run the script - this may take a few seconds.
