import subprocess
import time
import re
import cv2
import os

# --- Helper function for capturing images using rpicam-jpeg ---
def capture_image_with_rpicam_jpeg(camera_id_0_based, output_filename, resolution=(1920, 1080), exposure_us=None, quality=90):
    """
    Captures a single image from the specified camera using rpicam-jpeg.
    Includes --info-text for detailed diagnostics.
    
    Args:
        camera_id_0_based (int): The 0-based index of the camera to use.
        output_filename (str): The path to save the JPEG image.
        resolution (tuple): A tuple (width, height) for the image resolution.
        exposure_us (int, optional): Manual exposure time in microseconds. If None, auto-exposure is used.
        quality (int): JPEG compression quality (0-100).
    
    Returns:
        bool: True if image capture was successful, False otherwise.
    """
    cmd = [
        'rpicam-jpeg', 
        '-c', str(camera_id_0_based),
        '--output', output_filename,
        '--width', str(resolution[0]),
        '--height', str(resolution[1]),
        '--quality', str(quality),
        '--timeout', '1000', # Increased timeout to 1 second for reliability
        '--info-text', '%md' # Outputs metadata to stderr, useful for debugging
    ]

    if exposure_us is not None:
        cmd.extend(['--shutter', str(exposure_us)])

    print(f"\n  Attempting capture for Camera ID {camera_id_0_based}:")
    print(f"  Executing command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False) # Check=False to handle errors gracefully
        
        # Always print stderr for debugging
        if result.stderr:
            print("  --- rpicam-jpeg STDERR Output (Diagnostics) ---")
            print(result.stderr.strip())
            print("  -------------------------------------------------")
        
        if result.returncode == 0:
            print(f"  SUCCESS: Image captured to {output_filename}")
            return True
        else:
            print(f"  FAILURE: Command exited with code {result.returncode}")
            print(f"  Stdout: {result.stdout.strip()}") # May contain some info even on error
            print(f"  Possible reasons: Resolution not supported, camera busy, or driver issue.")
            return False
    except FileNotFoundError:
        print("  Error: 'rpicam-jpeg' command not found. Ensure libcamera-apps is installed and in your PATH.")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred during capture: {e}")
        return False



# --- Function to get cameras from 'cam -l' ---
def get_libcamera_devices():
    """
    Executes 'cam -l' and parses its output to map
    libcamera IDs to camera names and paths.
    Returns a list of dictionaries, each with 'id_1_based', 'id_0_based',
    'name', and 'path' for cameras detected by libcamera.
    """
    print("Attempting to list libcamera devices using 'cam -l'...")
    try:
        # Run the command, capture output
        result = subprocess.run(
            ["cam", "-l"],
            capture_output=True,
            text=True,
            check=False, # Don't raise an error immediately, check returncode
        )

        if result.returncode != 0:
            print(f"Warning: 'cam -l' exited with code {result.returncode}.")
            print(f"Stderr: {result.stderr.strip()}")
            return []

        output_lines = result.stdout.strip().split("\n")

    except FileNotFoundError:
        print("Error: 'cam' command not found.")
        print("Please ensure libcamera-apps (which includes 'cam') is installed and in your PATH.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while trying to run 'cam -l': {e}")
        return []

    libcamera_devices = []
    parsing_cameras = False
    for line in output_lines:
        line = line.strip()
        if not line:
            continue

        if "Available cameras:" in line:
            parsing_cameras = True
            continue

        if parsing_cameras:
            # Regex to extract camera ID (1-based), name, and path
            match = re.match(r'(\d+):\s+\'([^\']+)\'\s+\(([^\)]+)\)', line)
            if match:
                id_1_based = int(match.group(1))
                name = match.group(2)
                path = match.group(3)
                
                # Convert to 0-based index for tools like rpicam-jpeg/still
                id_0_based = id_1_based - 1 

                libcamera_devices.append({
                    "id_1_based": id_1_based,
                    "id_0_based": id_0_based,
                    "name": name,
                    "path": path,
                    "opencv_index": None # Placeholder for OpenCV index
                })
            else:
                # Stop parsing if we encounter a line that doesn't match the camera format
                # This helps prevent parsing extraneous log messages below the camera list
                break 
    return libcamera_devices


# --- The main function with the modified capture loop ---
def main():
    print("--- Camera Discovery and Compatibility Check ---")

    # Step 1: Get devices detected by libcamera
    libcamera_devices = get_libcamera_devices()
    if not libcamera_devices:
        print("\nNo cameras detected by 'cam -l'. Please ensure cameras are connected and libcamera is working.")
        print("Exiting.")
        return

    # Step 3: Combine and present the information
    print("\n      --- Summary of Detected Cameras ---      ")
    print("-------------------------------------------------")


    if libcamera_devices:
        print("\nCameras Detected by 'cam -l' (libcamera):")
        for lc_cam in libcamera_devices:
            print(f"  Libcamera ID (0-based): {lc_cam['id_0_based']}")
            print(f"  Name:                     '{lc_cam['name']}'")
            print(f"  Path:                     '{lc_cam['path']}'")
            print("-------------------------------------------------")
    else:
        print("No cameras detected by 'cam -l'.")
        print("-------------------------------------------------")

    # --- New Section: Demo Image Capture from ALL libcamera-detected cameras ---
    print("\n--- Demo Image Capture from ALL Libcamera-Detected Cameras ---")
    output_dir = "demo_images"
    os.makedirs(output_dir, exist_ok=True) # Ensure output directory exists

    if libcamera_devices:
        for cam_info in libcamera_devices:
            camera_id_0_based = cam_info['id_0_based']
            camera_name_sanitized = re.sub(r'[^\w\s.-]', '', cam_info['name']).replace(" ", "_") # Sanitize name for filename
            timestamp = int(time.time())
            
            # Default resolution for demo. Start with a common one.
            # If a camera consistently fails, try lowering this.
            demo_resolution = (1920, 1080) 
            
            output_filename = os.path.join(output_dir, f"cam_{camera_id_0_based}_{camera_name_sanitized}_{timestamp}.jpg")
            
            print(f"\nProcessing Camera ID {camera_id_0_based} ('{cam_info['name']}')")
            print(f"  Output file: {output_filename}")
            
            # Use auto-exposure for simplicity in a general demo
            # Consider adding a small delay between captures if issues persist
            # time.sleep(0.5) 
            
            success = capture_image_with_rpicam_jpeg(
                camera_id_0_based, 
                output_filename, 
                resolution=demo_resolution, 
                exposure_us=None # Auto exposure
            )
            
            if not success:
                print(f"  --- Capture failed for Camera ID {camera_id_0_based} ('{cam_info['name']}') ---")
                # Attempt with a lower resolution if the first try failed
                print(f"  Attempting capture for Camera ID {camera_id_0_based} at 640x480 resolution as fallback...")
                output_filename_fallback = os.path.join(output_dir, f"cam_{camera_id_0_based}_{camera_name_sanitized}_{timestamp}_fallback.jpg")
                capture_image_with_rpicam_jpeg(
                    camera_id_0_based, 
                    output_filename_fallback, 
                    resolution=(640, 480), 
                    exposure_us=None
                )
            
    else:
        print("No cameras detected by 'cam -l'. No demo images to capture.")

    print("\n-------------------------------------------------")


if __name__ == "__main__":
    main()
