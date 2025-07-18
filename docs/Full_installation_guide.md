# Phorest Pipeline: Field Engineer Installation Guide

This document provides instructions for the initial setup, calibration, and long-term deployment of the Phorest Pipeline system in a field environment.

---
## Part 1: Initial System Setup

This section covers the one-time setup for connecting to the Pi and preparing the system for calibration.

### 1.1. Network Connection
* Connect the Phorest Pi directly to the laptop via an Ethernet cable.
* On the laptop, ensure the **`Pi Direct Connection`** network profile is active. The Pi will be available at the static IP address `192.168.1.2`.

### 1.2. Accessing the Pi
* **Terminal Access:** Open a terminal on the laptop and connect to the Pi via SSH.
    ```bash
    ssh <username>@192.168.1.2
    ```
* **File Access:** Open the file explorer on the laptop. If a bookmark for the Pi is not present, connect to the server using the address `sftp://<username>@192.168.1.2`. It is recommended to bookmark both the project folder and the data storage folder (`/mnt/phorest_data` or similar) for easy access.

---
## Part 2: System Calibration

This is a mandatory process to be performed after any new physical installation or significant change to the sample stage.

### 2.1. Launch the TUI
From your SSH session on the Pi, launch the main TUI application.
```bash
phorest
```

### 2.2. Pre-flight Checks
Before calibration, run these initial checks from the TUI menu:

* **`Check USB Storage`**: Ensures the external data drive is mounted and accessible.
* **`Iniatialise Directories`**: Verifies that all necessary data and results folders exist.

### 2.3. Camera and Feature Calibration
This is an iterative process to align the system's analysis with the camera's view.

1.  **Configure Camera**: Open `configs/Phorest_config.toml` and ensure the `camera_type` and other parameters in the `[Camera]` section are correct for the installed hardware.
2.  **Align Sample**:
    * If available, run **`continuous_image_preview.sh`**, this script will be located on the Desktop, if you are running 'headless' from the TUI menu, select the **`Start Continuous Image Capture`** option. This will save an image (and continue to overwrite) to the `continuous_capture/` called `continuous_capture_frame.jpg` - this 'live' preview will be at a very low framerate so using a move sample / check resulting image / repeat approach will be required.
    * Physically adjust your sample and the camera's focus until the chip is clear and correctly positioned.
    * Return to the `configs/Phorest_config.toml` file and adjust the camera settings (like `camera_exposure`, `camera_brightness`) to improve the image quality.
    * Stop the continuous capture from the TUI by navigating to **`MANAGE Running processes separately`**, selecting `run_continuous_capture.py`, and pressing 'K'.
    * Repeat this step as needed until you are happy with the image.
    * Note: if you have used **`continuous_image_preview.sh`** script, you will need to run the **`Start Continuous Image Capture`** option to check the image quality of the full-size images that will be captured during the experiment (pay close attention to the images brightness, and contrast, these can be adjusted in the `configs/Phorest_config.toml` see Step 2).
3.  **Define Feature Locations**:
    * Ensure a clear reference image exists in the `continuous_capture/` directory.
    * Open `configs/Feature_locations.toml`. Using an image viewer to find pixel coordinates, update the `[[features]]` table with the `label` and `feature_location` of at least two visible features.
4.  **Generate ROI Manifest**:
    * In the TUI, select the **`Locate Gratings in Image`** option. The script will run for a few moments.
    * **On Success** (green text output), check the `generated_files/` directory. Open the `Label_locations.png` and `Grating_locations.png` images to visually confirm that the software has correctly identified all the features and gratings.
    * **On Failure** (red text output), or if the generated images are incorrect, you have a few options:
        * Go back to **Step 5** and choose different, clearer labels.
        * Go back to **Step 3** to improve the sample's focus and alignment.
        * As a last resort, you can create the `generated_files/ROI_manifest.json` file manually.

---
## Part 3: Long-Term Experiment Deployment

### 3.1. Final Configuration Check
* Open `configs/Phorest_config.toml` one last time.
* Verify all timing intervals (`collector_interval_seconds`, `file_backup_interval_seconds`, etc.) are set correctly for the long-term run.
* Ensure the `root_dir` is pointing to the correct external storage location.

### 3.2. Starting the Pipeline
* From the TUI main menu, select **`START All processes for Data collection`**. This will launch all necessary background services.
* The TUI will confirm that the processes have started. You can now safely exit the TUI (press 'Q') and close the SSH session. The pipeline will continue to run in the background.

### 3.3. Stopping the Pipeline
* To stop the experiment, reconnect to the Pi via SSH and launch the TUI again (`python phorest.py`).
* Select **`STOP All Data collection processes`**.
* **Note:** The scripts are designed for a graceful shutdown and will finish their current tasks before stopping. This may take a few moments.

### 3.4. Data Retrieval
* After stopping all processes, connect to the Pi's file system as described in section 1.2.
* Copy the required data from the data storage directory (`/mnt/phorest_data` or similar).
* **Important:** Do not delete or move the top-level folders (`data`, `results`, etc.) from the Pi, as they are required for the pipeline to function correctly.