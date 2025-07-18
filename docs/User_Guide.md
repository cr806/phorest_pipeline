## Phorest Pipeline User Guide 🔬

This guide provides step-by-step instructions for setting up and running a standard data collection experiment using the Phorest Pipeline software.

---
### Part 1: Setup & Calibration

This section covers the initial one-time setup required before you can begin an automated experiment.

#### **Step 1: Start the TUI**
Before you begin, open a terminal and launch the main Text-based User Interface (TUI), by entering ``` phorest ``` and pressing <Enter>

#### **Step 2: Configure the Experiment**
Open the main configuration file located at `configs/Phorest_config.toml` in a text editor. Update the settings for your experiment, paying close attention to the `[Camera]` section to ensure the correct `camera_type` is selected.

#### **Step 3: Align and Focus the Sample**
This is an iterative process to get a clear and centered image.

1.  If available, run **`continuous_image_preview.sh`**, this script will be located on the Desktop, if you are running 'headless' from the TUI menu, select the **`Start Continuous Image Capture`** option. This will save an image (and continue to overwrite) to the `continuous_capture/` called `continuous_capture_frame.jpg` - this 'live' preview will be at a very low framerate so using a move sample / check resulting image / repeat approach will be required.
2.  Physically adjust your sample and the camera's focus until the chip is clear and correctly positioned.
3.  Return to the `configs/Phorest_config.toml` file and adjust the camera settings (like `camera_exposure`, `camera_brightness`) to improve the image quality.
4.  Stop the continuous capture from the TUI by navigating to **`MANAGE Running processes separately`**, selecting `run_continuous_capture.py`, and pressing 'K'.
5.  Repeat this step as needed until you are happy with the image.
6.  Note: if you have used **`continuous_image_preview.sh`** script, you will need to run the **`Start Continuous Image Capture`** option to check the image quality of the full-size images that will be captured during the experiment (pay close attention to the images brightness, and contrast, these can be adjusted in the `configs/Phorest_config.toml` see Step 2).

#### **Step 4: Capture a Reference Image**
Ensure the `continuous_capture/` directory contains one good example image (e.g., `continuous_capture_frame.jpg`) from the previous step. This image will be used for the next calibration step.

#### **Step 5: Define Feature Locations**
1.  Open the reference image from the `continuous_capture/` directory in an external image viewing program that can display pixel coordinates.
2.  Open the feature location config file at `configs/Feature_locations.toml`.
3.  Identify a few distinct labels visible in your reference image.
4.  Update the `[[features]]` table in the `configs/Feature_locations.toml` file with the `label` name and its rough pixel `feature_location = [x, y]` for each feature you've chosen (see notes in `Feature_locations.toml` file for how to reference chip labels).

#### **Step 6: Generate and Verify the ROI Manifest**
This step uses your defined features to automatically find all regions of interest (ROIs) on the sample.

1.  In the TUI, select the **`Locate Gratings in Image`** option. The script will run for a few moments.
2.  **On Success** (green text output), check the `generated_files/` directory. Open the `Label_locations.png` and `Grating_locations.png` images to visually confirm that the software has correctly identified all the features and gratings.
3.  **On Failure** (red text output), or if the generated images are incorrect, you have a few options:
    * Go back to **Step 5** and choose different, clearer labels.
    * Go back to **Step 3** to improve the sample's focus and alignment.
    * As a last resort, you can create the `generated_files/ROI_manifest.json` file manually.

You are now calibrated and ready to run an experiment! 🎉

---
### Part 2: Running an Experiment

#### **Step 1: Set the Data Save Location**
Before starting, double-check your `configs/Phorest_config.toml` file one last time. Ensure the `root_dir` under the `[Paths]` section is set to the correct location for your experiment's data (e.g., your external USB drive, or network storage).

#### **Step 2: Start the Pipeline Scripts**
From the TUI main menu, you have two options:
* To run the entire standard pipeline, select **`START All processes for Data collection`**.
* To run only specific parts of the pipeline, select the individual scripts you need (e.g., **`(Start Periodic Image Collection Process)`**, **`(Start Image Analysis Process)`**, etc.) one by one.

The scripts are now running in the background and will continue even if you close the TUI terminal.

---
### Part 3: Finishing the Experiment & Troubleshooting

#### **Step 1: Stop the Pipeline Scripts**
When your experiment is complete, open the TUI again.
* To stop all running services at once, select **`STOP All Data collection processes`**.
* To stop them individually, select **`MANAGE Running processes separately`**, navigate to the script you want to stop, and press 'K'.

**Note:** The scripts will not stop instantly. They have been designed to shut down gracefully and will finish their current task (e.g., processing a batch of images) before exiting.

#### **Step 2: Check the Logs**
If you are unsure about the status of the system or if something seems wrong, you can check the log files located in the `logs/` directory. Each script (`collector.log`, `processor.log`, etc.) has its own detailed log file.
