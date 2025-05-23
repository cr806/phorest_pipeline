## Instructions for use

# Initial laptop and phorest-pi setup
- Plug phorest-pi, using any ethernet cable, directly into the laptop
- Go to network settings on the laptop and ensure that `Pi direct connection` is available
- Switch on the phorest-pi, after booting, the pi should revert to a static IP configuration, at this point the laptop's `Pi direct connection` should refresh to say it's connected and using IP 192.168.1.1
- The phorest-pi should now be available at IP 192.168.1.2

# To access phorest config files and data
- Open file explorer on laptop, in the right-hand panel there should be a location `phorest-pipeline` bookmarked - this is a mapping to the phorest-pi.  There should also be a bookmark for `ARGUS_data` another mapping to the pi.
- If the location is not mapped, click on 'Other Connections' in right-hand panel, then at bottom of panel enter, into the 'Connect to server' sftp://phorest@192.168.1.2, then press connect.  Navigate to the /Documents/Python/phorest-pipeline.  Bookmark this location.  Now navigate to /mnt/ARGUS_data and bookmark this location too.
- To get data off the pi, first stop all phorest processes (see below), now copy the require data from the `ARGUS_data` directory.  DO NOT delete, or remove any of the folders from the Pi, these are required to be in place for the data collection phorest processes.

# Running the phorest processes
- Open a terminal on the laptop
- Enter `ssh benjamin` (yes, the phorest-pi is called Benjamin)
- Navigate to the project directory
  `cd Documents/Python/phorest-pipeline`
- Run master process controller TUI
  `uv run phorest.py`

# Using phorest.py
# After computer reboot - possibly after copying data off the USB stick (this should not be needed with the connection to the laptop)
1. Check USB storage is mounted and accessible
   `Check USB Storage`
    - report any errors to Phorest (unless you're comfortable to fix them)
2. Create storage directories
   `Iniatialise Directories`
    - this will check and if neccessary create the directories required for all phorest processes

# Set-up phorest processes
3. Search for and return camera index (required for Phorest_config.toml file) results will be displayed on screen
   `Find Camera Index` 
4. Search for and return thermocouple serial numbers (require for Phorest_config.toml file) results will be displayed on screen
   `Find Thermocouple Serial Numbers`
5. Collect images continuously (used for chip alignment, also required for locating gratings)
   a. update 'Phorest_config.toml' to match your choice of camera, camera index (see step 4), and camera parameters (i.e. exposure time)
   `Start Continuous Image Capture`
   b. to stop continuous capture 
   `MAINTAIN processes running in background`, then selecting continuous capture script and press `k`
   Notes:
   - images will be saved to 'continuous_capture' directory
   - suggested use for optimising camera parameters i.e. exposure time, aligning/focussing a new chip installation
      - NB: changes to camera parameters are only registered after `continuous capture` has been stopped and restarted
      - NB: image refresh rate will be low, as each image is being captured and saved to disk
6. Determine location of gratings in field-of-view
   a. update 'Feature_locations.toml' with at least two labels and pixel locations
   - use an image from the 'continuous_capture' directory and any image manipulation software for this (e.g. imageJ)
   `Locate Gratings in Image`
   Notes:
   - you will now have a number of files in the 'generated_files' directory
   - before moving on to step 3, check the grating locations using the 'Grating_locations.png' from the 'generated_files' directory
   - if grating locations are not correct, and repeating this process has not improved their location, generate the 'ROI_manifest.json' file manually using any image manipulation software for the pixel locations / grating sizes (in pixels)

# Start data collection
7. Either start phorest processes independently (see below) or all at once
   `START All data collection processes`
(Optional)
  1. Start data collection
     - Ensure 'Phorest_config.toml' matches your timing intervals, choice of camera, camera parameters (i.e. exposure time)
     `Start Periodic Image Collection Process`
  2. Start periodic data analysis
     `Start Image Analysis Process`
  3. Start periodic data plotter
     `Start Data Plotting Process`
  4. Start periodic image compressor
     `Start Data Compression Process`
      NB: periodically (see parameter in 'Phorest_config.toml') this script will convert all images fron png to webp format (in the process compressing them)
  5. Start periodic file backup
     `Start File Backup Process`
      NB: periodically (see parameter in 'Phorest_config.toml') this script will back-up and zip all data and results files to the 'Back up' directory
  Notes: all these steps will start each process in the background so that the remote session can be closed without stopping data collection

# Stop data collection (and other phorest processes)
8. Either stop all processes independently (see below) or all at once
   `STOP All data collection processes`
(Optional)
  1. Select `MAINTAIN processes running in background`
  2. Select each process in turn and press `k` to stop
  3. Press `Q` to return to main menu

# Finally
9. At any point in the main menu, press `Q` to quit, any processes that have been started will continue to run
10. Run `uv run phorest.py` to start the master process controller TUI again, running processes will be listed and can be controlled (i.e. stopped or started again) as outlined above
