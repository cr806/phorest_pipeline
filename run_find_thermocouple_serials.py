import subprocess
import time
from pathlib import Path

# Define ANSI color codes for better terminal output
# COLOR_GREEN = "\033[92m"
# COLOR_RED = "\033[91m"
# COLOR_YELLOW = "\033[93m"
# COLOR_BLUE = "\033[94m"
# COLOR_END = "\033[0m"  # Resets the color

# Location where 1-Wire devices are exposed in the Linux file system
DEVICE_LOC = Path("/sys/bus/w1/devices/")


def load_w1_modules():
    """
    Loads the necessary 1-Wire kernel modules (w1-gpio and w1-therm).
    Requires root privileges to execute these commands.
    """
    print("Attempting to load 1-Wire kernel modules (requires sudo/root privileges)...")
    try:
        # These commands need sudo permissions to run successfully
        # We use subprocess.run for better control and error checking
        subprocess.run(["sudo", "modprobe", "w1-gpio"], check=True, capture_output=True)
        subprocess.run(["sudo", "modprobe", "w1-therm"], check=True, capture_output=True)
        print("1-Wire modules loaded successfully.")
        time.sleep(0.5)  # Give the system a moment to recognize devices
    except FileNotFoundError:
        print("Error: 'sudo' or 'modprobe' command not found. Ensure they are in your PATH.")
        print("You might need to install 'sudo' or 'kmod' package.")
        return False
    except subprocess.CalledProcessError as e:
        print(
            "Error loading 1-Wire modules. Make sure you have sudo privileges and that 1-Wire is enabled."
        )
        print(f"Stdout: {e.stdout.decode().strip()}")
        print(f"Stderr: {e.stderr.decode().strip()}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while loading 1-Wire modules: {e}")
        return False
    return True


def find_thermocouple_serial_numbers():
    """
    Scans the 1-Wire device directory for connected DS18B20 temperature sensors.
    These devices typically have serial numbers starting with '28-'.

    Returns:
        list: A list of found serial number strings.
    """
    print(f"\nScanning for 1-Wire devices in: {DEVICE_LOC}")
    found_serials = []
    if not DEVICE_LOC.is_dir():
        print(
            f"[ERROR]: 1-Wire device directory not found at {DEVICE_LOC}. Is 1-Wire enabled and modules loaded?"
        )
        return []

    # Iterate through all subdirectories in DEVICE_LOC
    for device_path in DEVICE_LOC.iterdir():
        # 1-Wire temperature sensors (DS18B20) typically have serials starting with '28-'
        if device_path.is_dir() and device_path.name.startswith("28-"):
            serial_number = device_path.name
            # Optionally, check if the w1_slave file exists and is readable
            if Path(device_path, "w1_slave").is_file():
                found_serials.append(serial_number)
                print(f"  Found 1-Wire device: {serial_number}")
            else:
                print(
                    f"  Found directory '{serial_number}', but 'w1_slave' file is missing or unreadable."
                )

    return found_serials


def main():
    print("--- 1-Wire Thermocouple Serial Number Finder ---")
    print("--------------------------------------------------")

    # Step 1: Load 1-Wire modules (requires sudo/root)
    if not load_w1_modules():
        print("Cannot proceed without 1-Wire modules loaded. Please resolve the issue above.")
        print("--------------------------------------------------")
        return

    # Step 2: Find serial numbers
    serial_numbers = find_thermocouple_serial_numbers()

    # --- Summary ---
    print("")
    print("")
    print("\n     --- Summary of Found Thermocouples ---     ")
    print("--------------------------------------------------")

    if serial_numbers:
        print(
            f"Successfully found {len(serial_numbers)} 1-Wire temperature sensor(s):"
            # f"{COLOR_GREEN}Successfully found {len(serial_numbers)} 1-Wire temperature sensor(s):"
        )
        for idx, serial in enumerate(serial_numbers):
            print(f"  Serial Number:       {serial}")
        print("--------------------------------------------------")
        print("")
        print("")
    else:
        print(
            "No 1-Wire temperature sensors (devices starting with '28-') were found."
            # f"{COLOR_RED}No 1-Wire temperature sensors (devices starting with '28-') were found."
        )
        print("Possible reasons:")
        print("  - Sensors not physically connected to the 1-Wire bus.")
        print(
            "  - 1-Wire not properly configured or enabled on your system (e.g., in /boot/config.txt for Raspberry Pi)."
        )
        print(
            "  - Required kernel modules ('w1-gpio', 'w1-therm') failed to load (check messages above)."
        )
        print("--------------------------------------------------")

    # # --- Summary ---
    # print("")
    # print("")
    # print(f"\n{COLOR_BLUE}     --- Summary of Found Thermocouples ---     {COLOR_END}")
    # print(f"{COLOR_BLUE}--------------------------------------------------{COLOR_END}")

    # if serial_numbers:
    #     print(
    #         f"{COLOR_GREEN}Successfully found {len(serial_numbers)} 1-Wire temperature sensor(s):{COLOR_END}"
    #     )
    #     for idx, serial in enumerate(serial_numbers):
    #         print(f"  {COLOR_YELLOW}Serial Number:      {COLOR_END} {serial}")
    #     print(f"{COLOR_BLUE}--------------------------------------------------{COLOR_END}")
    #     print("")
    #     print("")
    # else:
    #     print(
    #         f"{COLOR_RED}No 1-Wire temperature sensors (devices starting with '28-') were found.{COLOR_END}"
    #     )
    #     print("Possible reasons:")
    #     print("  - Sensors not physically connected to the 1-Wire bus.")
    #     print(
    #         "  - 1-Wire not properly configured or enabled on your system (e.g., in /boot/config.txt for Raspberry Pi)."
    #     )
    #     print(
    #         "  - Required kernel modules ('w1-gpio', 'w1-therm') failed to load (check messages above)."
    #     )
    #     print(f"{COLOR_BLUE}--------------------------------------------------{COLOR_END}")


if __name__ == "__main__":
    main()
