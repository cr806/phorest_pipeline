# Phorest Pipeline

Phorest Pipeline is a multi-process data collection and analysis application designed for long-running scientific experiments. It provides a modular framework for capturing image and sensor data, processing it in near real-time, and communicating the results through various handlers.

The system is built to be resilient, with features like graceful shutdown, concurrent file locking, and a local-first data strategy to ensure data integrity even during network interruptions.

---

## Key Features

* **Modular Architecture**: Each core task (Collector, Processor, Compressor, etc.) runs as an independent, class-based process, making the system easy to maintain and extend.
* **Concurrent & Safe**: Uses a file-based locking mechanism (`fcntl`) to prevent race conditions and data corruption when multiple processes access shared manifest files.
* **Graceful Shutdown**: All services handle `SIGINT` and `SIGTERM` signals to finish their current work cycle before exiting, preventing data loss or state inconsistency on shutdown.
* **Flexible Data Sources**: Easily configurable to use different camera types or even import legacy data from a directory of existing images.
* **Extensible Communication**: A dispatch system allows for different "communication" handlers to be used for reporting results, with current support for CSV/Plot generation and a clear path for future OPC-UA integration.
* **Resilient Network Syncing**: An optional `syncer` process provides a local-first data strategy, ensuring the pipeline continues to run smoothly even if the remote network storage is unavailable.
* **Automated Storage Management**: Includes a "sync-aware" ring buffer to manage local disk space by deleting the oldest *synced* images, preventing data loss while managing storage.

---

## System Architecture

The pipeline operates on a decoupled, file-based messaging pattern where scripts communicate asynchronously.

* **State Management**: The core of the system is the `data/metadata_manifest.json` file, which acts as a central task queue and state record for every image captured.
* **Results Logging**: Analysis results are appended to a scalable `results/processing_results.jsonl` file, which is designed to handle very large datasets without performance degradation.
* **Data Flow**:
    1.  The **Collector** captures data and adds a `pending` entry to the manifest.
    2.  The **Processor** finds `pending` entries, marks them as `processing`, analyzes the data, writes to the results log, and finally marks the manifest entry as `processed`.
    3.  The **Communicator** reads the manifests to generate reports and marks entries as `data_transmitted`.
    4.  Optional services like the **Compressor** and **Syncer** perform their tasks by reading and updating the state in the central manifest.

---

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

* A Raspberry Pi with Raspberry Pi OS (or a similar Debian-based Linux system).
* Python 3.10+
* `uv` (recommended) or `pip` for package management.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd phorest-pipeline
    ```

2.  **Sync the virtual environment and install dependencies:**
    ```bash
    uv sync
    ```

3.  **Activate the environment for your current session:**
    ```bash
    source .venv/bin/activate
    ```


### 1. Configuration

All system behavior is controlled via TOML configuration files located in the `configs/` directory.

* **`Phorest_config.toml`**: The main configuration file. Set all timing intervals, enable/disable components (camera, syncer, etc.), and define file paths here.
* **`Feature_locations.toml`**: Used during the calibration step to define the initial features for ROI detection.

### 2. Calibration

Before running an experiment, the system must be calibrated. This is done via the main Text-based User Interface (TUI).

```bash
python phorest.py
```

Follow the on-screen options to:

1.  **`Start Continuous Image Capture`** to align and focus the sample.
2.  **`Locate Gratings in Image`** to automatically generate the `ROI_manifest.json`.

*(For detailed instructions, please see the User Guide documentation).*

### 3. Running the Pipeline

Once calibrated, the entire pipeline can be started from the TUI:

* Select **`START All processes for Data collection`** to launch all services.
* The processes will run in the background. You can safely close the TUI and your SSH session.
* To stop the pipeline, re-launch the TUI and select **`STOP All Data collection processes`**.

---

## Extending the Pipeline

The system is designed to be extensible. To add a new communication method (e.g., for OPC-UA):

1.  Create a new handler module in `phorest_pipeline/communicator/outputs/`.
2.  Add a new member to the `CommunicationMethod` enum in `phorest_pipeline/shared/enums.py`.
3.  Map the new enum member to your handler function in the `COMMUNICATION_DISPATCH_MAP` in `phorest_pipeline/communicator/logic.py`.

---