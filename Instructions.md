## Instructions for use

# After computer boot
1. Check USB storage is mounted and accessible
  - run `run_storage_check`
    - report any errors to Phorest (unless you're comfortable to fix them)
2. Create storage directories
  - run `run_create_directories`
    - this will create the directories required and symlink these directories into the project directory
    - once complete all 'directories' will be accessible from the project directory root

# Start data collection
3. Collect an image of the aligned chip
  - update 'config.ini' to match your choice of camera, and camera parameters (i.e. exposure time)
  - run `run_continuous_capture`, stop by pressing `Ctrl-C`
  - images will be saved to 'continuous_capture' directory at project root
    - optimise camera parameters i.e. exposure time
      - NB: any change to camera parameters will only be registered after `run_continuous_capture` has been stopped and restarted
    - use generated images to align / focus chip
    - NB: image refresh rate will be low, as each image is being captured and saved to disk
4. Determine location of gratings in field-of-view
  - update 'Feature_locations.json' with at least two labels and pixel locations
    - use an image from the 'continuous_capture' directory and any image manipulation software for this (e.g. imageJ)
  - run `prepare_files_for_image_analysis`
    - this will step you through the process
  - you should now have a number of files in the 'generated_files' directory
  - before moving on to step 3, check the grating locations using the 'Grating_locations.png' from the 'generated_files' directory
  - if grating locations are not correct, and repeating this process has not improved their location, generate the 'ROI_manifest.json' file manually using any image manipulation software for the pixel locations / grating sizes (in pixels)
5. Start data collection
  - update 'config.ini' to match your timing intervals, choice of camera, camera parameters (i.e. exposure time) - some of these will have been done at step 1
  - run `run_collector`, start this process in the background so that the remote session can be closed without stopping data collection
6. Start data analysis
  - run `run_processor`, again as a background process
7. Start data plotter
  - run `run_communicator`
8. Start image compressor
  - run `run_compressor` - periodically (see parameter in 'config.ini') this script will convert all images fron png to webp format
