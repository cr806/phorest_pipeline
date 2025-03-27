# Process Pipeline

A multi-process pipeline for data collection, processing, and communication using file flags.

## Setup

1. Clone repo.
2. `uv venv .venv`
3. `source .venv/bin/activate`
4. `uv pip install -e .`
5. Ensure `flags/`, `data/`, `results/` directories exist.

## Running

Open three separate terminals, activate the virtual environment in each (`source .venv/bin/activate`), and run:

Terminal 1: `python run_collector.py`
Terminal 2: `python run_processor.py`
Terminal 3: `python run_communicator.py`
