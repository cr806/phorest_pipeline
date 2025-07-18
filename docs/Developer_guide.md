# Phorest Pipeline: Developer Guide

This document provides a technical overview of the Phorest Pipeline architecture for developers looking to understand, maintain, or extend the system.

---
## Core Architecture

The pipeline is a multi-process system designed for concurrent, resilient data collection and analysis. It is built on several key architectural principles:

* **State Machines**: Each core process (`collector`, `processor`, `syncer`, etc.) operates as a self-contained state machine.
* **Decoupling via Filesystem**: The scripts do not communicate directly. Instead, they are decoupled using manifest files on the filesystem, which act as a message queue.
    * `data/metadata_manifest.json`: The central "task queue" and state record for all images.
    * `results/processing_results.jsonl`: An append-only log of all analysis results.
* **File Locking**: To prevent race conditions and data corruption when multiple processes access the same manifest file, the system uses an `fcntl`-based file locking mechanism, which is encapsulated in the `metadata_manager`.
* **Graceful Shutdown**: All long-running processes use signal handlers to catch `SIGINT` and `SIGTERM`. This allows them to finish their current work cycle (e.g., processing a batch of images) before exiting, ensuring data consistency.
* **Class-Based Encapsulation**: Each process's logic and state are encapsulated within a dedicated class (e.g., `Collector`, `Processor`) to eliminate writable global variables.

#### Local Storage Management: The Ring Buffer

To prevent the local disk from filling up, a **ring buffer** mechanism is implemented within the `collector` script.

* **Purpose**: The primary goal is to maintain a fixed number of recent images on the local drive, defined by the `image_buffer_size` in the configuration. After each successful image collection, this function checks the total number of images in the `data` directory. If the count exceeds the buffer size, it deletes the oldest files until the limit is met.
* **Sync-Aware Logic**: The ring buffer is designed to work safely with the `syncer` process. If the `syncer` is enabled in the configuration, the ring buffer will **not** delete any old image that has not yet been successfully synced to the network drive (i.e., its `image_synced` flag in the manifest is `false`). This is a critical feature to prevent data loss in network deployments, as it ensures an image is archived remotely before its local copy is removed.

---
## The Pipeline Components

The pipeline consists of several independent, long-running Python scripts.

* **`collector`**: The entry point for data. It captures images and/or sensor readings at a set interval, creating a new "pending" entry for each one in the `metadata_manifest.json`.
* **`processor`**: The main data analysis engine. It watches the manifest for "pending" entries, claims a small chunk by marking them as "processing", performs the image analysis, appends the detailed results to `processing_results.jsonl`, and finally updates the manifest entries to "processed".
* **`communicator`**: The reporting/communicating engine. It reads both manifests to generate human-readable outputs like `communicating_results.csv` and `processed_data_plot.png`.
* **`communicator`**: The reporting and external communication engine. Its job is to take processed data and transmit it to external systems. The behavior is determined by the `[Communication]` method set in the config file.
    * **`CSV_PLOT` (Current Implementation):** In this mode, the script reads the manifests and generates human-readable outputs `communicating_results.csv` and `processed_data_plot.png` for local review.
    * **`OPC_UA` (Future Implementation):** In this mode, the script will act as an **OPC-UA client**. It will connect to a configured OPC-UA server and write the latest analysis results (e.g., mean, median, max resonance) to specific nodes on the server. This will involve creating a new `opc_ua_handler.py` module in the `communicator/outputs/` directory that contains the logic for connecting to the server and updating the node values.
* **`compressor`**: A utility process that runs periodically to find processed images and archive them using `gzip` to save local disk space. It updates the manifest with the new `.gz` filename.
    * **Note on PNGs**: The `collector` currently saves images in the **`.png`** format. Since PNG is already a compressed format, applying `gzip` to it offers only a **modest space saving** (typically 5-15%). Therefore, running the compressor is often not essential for PNG-based workflows.
    * **Future Usefulness**: The camera controller sources can be modified to save in uncompressed formats like **`.tif`** or **`.bmp`**. In these scenarios, the `compressor` becomes extremely useful, as `gzip` will dramatically reduce the file size of these uncompressed images.
* **`file_backup`**: An archiving process. It periodically moves the "live" manifest and results files into a versioned backup directory to keep the live files from growing indefinitely.
* **`syncer`**: An optional process for network deployments that syncs local data to a remote share. The pipeline follows a **local-first** strategy for speed and resilience.
    * **Processing Awareness**: The `syncer` is aware of the `processor`'s state. It reads the `metadata_manifest.json` and will only move an image file from the local `data` directory *after* its `processing_status` has been set to `"processed"`. This guarantees that an image is never moved before the analysis is complete.
    * **Resilience**: All scripts write to the local disk first. This acts as a buffer, ensuring that data collection and processing can continue uninterrupted even if the network drive is temporarily unavailable. The `syncer` will automatically catch up on moving the files once the connection is restored.

---
## Data Flow: Lifecycle of an Image

Here is the step-by-step journey of a single data point through the pipeline:

1.  **Collection**: The `collector` captures `image_01.png`. It locks `metadata_manifest.json`, adds a new entry with `processing_status: "pending"`, and saves the file.
2.  **Processing**: The `processor` finds the "pending" entry. It locks the manifest, changes its status to `"processing"`, and saves. It then releases the lock and performs the time-consuming image analysis.
3.  **Result Logging**: After analysis, the `processor` locks `processing_results.jsonl` and appends a new line containing the detailed analysis results for `image_01.png`.
4.  **State Update**: The `processor` locks `metadata_manifest.json` again and updates the entry for `image_01.png`, changing its status to `"processed"`.
5.  **Reporting**: The `communicator` runs, loads both manifests, and regenerates the CSV and plot to include the new data from `image_01.png`. It then updates the `data_transmitted` flag in the `metadata_manifest.json` entry.
6.  **Compression (Optional)**: The `compressor` finds the "processed" entry for `image_01.png`. It creates `image_01.png.gz`, deletes the original, and updates the `filename` field in the manifest to `image_01.png.gz`.
7.  **Syncing (Optional)**: The `syncer` finds the "processed" entry. It moves `image_01.png.gz` to the network drive and updates the manifest by setting `image_synced: True` and changing its `filepath` to the new network location.
8.  **Cleanup**: Eventually, the `collector`'s `ring_buffer_cleanup` function determines that `image_01.png.gz` is one of the oldest files. Seeing that it has been synced (`image_synced: True`), it safely deletes the local copy to free up space.