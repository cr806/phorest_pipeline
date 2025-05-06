# phorest_pipeline/collector/thermocouple_controller.py
import datetime
import time
from pathlib import Path

DEVICE_LOC = Path('/sys/bus/w1/devices/')
DEVICE_DICT= {
    '28-00000ff8fa16': 'Sensor 1',
    '28-00000ff82fc2': 'Sensor 2',
}

def start_w1():
    pass


def check_device_connection(device_dict) -> bool:
    for sensor_id in device_dict:
        if not Path(DEVICE_LOC, sensor_id).exists():
            print(f'[THERMOCOUPLE] [ERROR] Device {sensor_id} not found at {DEVICE_LOC}.')
            return False
        else:
            print(f'[THERMOCOUPLE] Device {sensor_id} found at {DEVICE_LOC}.')


def read_sensor_ROM(device_id):
    with open(Path(DEVICE_LOC, device_id, 'w1_slave'), 'r') as f:
        return f.readlines()


def read_temp(device_id) -> tuple[int, str, float | None]:
    lines = read_sensor_ROM(device_id)
    error_count = 0
    while lines[0].strip()[-3:] != 'YES' and error_count < 5:
        time.sleep(0.2)
        lines = read_sensor_ROM(device_id)
        error_count += 1
    if error_count >= 5:
        return None
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        return float(temp_string) / 1000.0
    else:
        return None


def thermocouple_controller(data_dir: Path) -> tuple[int, str, dict | None]:
    """
    Reads thermocouples, saves data, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
    """
    print('[THERMOCOUPLE] --- Starting Thermocouple Controller ---')
    metadata_dict = None

    try:
        print('[THERMOCOUPLE] Checking sensor connections ...')
        if not check_device_connection(DEVICE_DICT):
            return (1, '[THERMOCOUPLE] [ERROR] Sensor(s) not found.', None)

        print('[THERMOCOUPLE] Taking temperature measurements ...')
        time.sleep(0.5)

        measurement_timestamp = datetime.datetime.now()
        temp_data = {
            'sensor_1': 25.5 + (time.time() % 1),
            'sensor_2': 30.1 - (time.time() % 0.5),
        }
        print(f'[THERMOCOUPLE] Measured: {temp_data}')

        metadata_dict = {
            'type': 'temperature',
            'timestamp_iso': measurement_timestamp.isoformat(),
            'data': temp_data,
            'error_flag': False,
            'error_message': None,
        }
        return (0, '[THERMOCOUPLE] Data captured successfully.', metadata_dict)

    except Exception as e:
        print(f'[THERMOCOUPLE] [ERROR] Unexpected error: {e}')
        metadata = {
            'type': 'temperature',
            'timestamp_iso': measurement_timestamp.isoformat(),
            'data': None,
            'error_flag': True,
            'error_message': f'Unexpected error: {e}',
        }
        return (1, f'[THERMOCOUPLE] [ERROR] Failed during operation: {e}', metadata)
    finally:
        print('[THERMOCOUPLE] --- Thermocouple Controller Done ---')
