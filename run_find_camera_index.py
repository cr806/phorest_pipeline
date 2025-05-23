import subprocess
import time

import cv2

# Define ANSI color codes
# These work in most modern terminals
# COLOR_GREEN = '\033[92m'
# COLOR_RED = '\033[91m'
# COLOR_YELLOW = '\033[93m'
# COLOR_BLUE = '\033[94m'
# COLOR_END = '\033[0m' # Resets the color


def get_v4l2_devices():
    """
    Executes 'v4l2-ctl --list-devices' and parses its output to map
    camera indices to human-readable camera names.
    Returns a dictionary where keys are integer device indices (e.g., 0, 1)
    and values are cleaned camera names (e.g., "Logitech Webcam C920").
    """
    print("Attempting to list V4L2 devices using 'v4l2-ctl --list-devices'...")
    try:
        # Run the command, capture output, and don't raise an error immediately if command fails
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print(f"Warning: 'v4l2-ctl' exited with code {result.returncode}.")
            print(f"Stderr: {result.stderr.strip()}")
            return {}

        output_lines = result.stdout.strip().split("\n")

    except FileNotFoundError:
        print("Error: 'v4l2-ctl' command not found.")
        print("Please install v4l-utils (e.g., 'sudo apt install v4l-utils' on Debian/Ubuntu,")
        print("or check your distribution's package manager for 'v4l-utils' or similar).")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred while trying to run 'v4l2-ctl': {e}")
        return {}

    camera_name_map = {}
    current_camera_name = "Unknown Camera"  # Default name if no specific name is found

    for line in output_lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("/dev/video"):
            try:
                device_index = int(line.replace("/dev/video", ""))
                camera_name_map[device_index] = current_camera_name
            except ValueError:
                pass
        else:
            name_parts = []
            in_parentheses = False
            for char in line:
                if char == "(":
                    in_parentheses = True
                elif char == ")":
                    in_parentheses = False
                elif not in_parentheses:
                    name_parts.append(char)
            current_camera_name = "".join(name_parts).strip()
            if current_camera_name.endswith(":"):
                current_camera_name = current_camera_name[:-1].strip()

    return camera_name_map


def find_working_cameras_opencv(v4l2_device_map: dict):
    """
    Iterates through potential camera indices (0-9) using OpenCV's VideoCapture
    and reports which cameras can be successfully opened and read from.

    Args:
        v4l2_device_map (dict): A dictionary mapping device indices to names
                                obtained from get_v4l2_devices().

    Returns:
        list: A list of dictionaries, each containing 'name' and 'index'
              for successfully detected cameras.
    """
    print("\nStarting OpenCV camera check (iterating indices 0-9)...")
    found_cameras = []

    for i in range(5):  # Check the first 5 common camera indices
        print(f"  Checking camera index {i}...")

        cap = cv2.VideoCapture(i)  # Attempt to open the camera at this index

        if not cap.isOpened():
            print(f"    Index {i}: Not accessible by OpenCV.")
            cap.release()  # Always release the camera object
            continue

        ret, _ = cap.read()
        if ret:
            camera_name = v4l2_device_map.get(i, f"Generic Camera (Index {i})")
            print(f"    SUCCESS: Camera '{camera_name}' found at index {i}.")
            found_cameras.append({"name": camera_name, "index": i})
        else:
            print(
                f"    Index {i}: Accessible, but could not read a frame (might be in use or faulty)."
            )

        cap.release()

        time.sleep(0.1)

    return found_cameras


def main():
    print("--- USB Camera Index Finder ---")

    # Step 1: Get device names from v4l2-ctl
    v4l2_map = get_v4l2_devices()
    if not v4l2_map:
        print(
            "\nNo V4L2 device information could be retrieved. Proceeding with generic OpenCV checks."
        )

    # Step 2: Use OpenCV to find working camera indices
    working_cameras = find_working_cameras_opencv(v4l2_map)

    # --- Summary of Detected Cameras ---
    print("")
    print("")
    print("\n      --- Summary of Detected Cameras ---      ")
    print("-------------------------------------------------")

    if working_cameras:
        for camera in working_cameras:
            print(f"Camera Name:                  '{camera['name']}'")
            print(f"Recommended Index for Config:  {camera['index']}")
            print("-------------------------------------------------")
        print("")
        print("")
    else:
        print("No working cameras found in the first 10 indices using OpenCV.")
        print(
            "Possible reasons: No camera connected, incorrect drivers, or insufficient permissions."
        )
        print("Ensure you have OpenCV (cv2) installed: 'pip install opencv-python'")
        print("-------------------------------------------------")

    # # --- Summary of Detected Cameras ---
    # print("")
    # print("")
    # print(f"\n{COLOR_BLUE}      --- Summary of Detected Cameras ---      {COLOR_END}")
    # print(f"{COLOR_BLUE}-------------------------------------------------{COLOR_END}")

    # if working_cameras:
    #     for camera in working_cameras:
    #         print(f"{COLOR_YELLOW}Camera Name:                 {COLOR_END} '{camera['name']}'")
    #         print(f"{COLOR_YELLOW}Recommended Index for Config:{COLOR_END}  {camera['index']}")
    #         print(f"{COLOR_BLUE}-------------------------------------------------{COLOR_END}")
    #     print("")
    #     print("")
    # else:
    #     print(f"{COLOR_RED}No working cameras found in the first 10 indices using OpenCV.{COLOR_END}")
    #     print("Possible reasons: No camera connected, incorrect drivers, or insufficient permissions.")
    #     print(f"Ensure you have OpenCV (cv2) installed: {COLOR_YELLOW}'pip install opencv-python'{COLOR_END}")
    #     print(f"{COLOR_BLUE}-------------------------------------------------{COLOR_END}")


if __name__ == "__main__":
    main()
