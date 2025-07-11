# phorest_pipeline/collector/thermocouple_controller.py
import datetime
import time
from pathlib import Path

from phorest_pipeline.shared.config import (
    THERMOCOUPLE_IDS,
)
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='data_source.log')

DEVICE_LOC = Path('/sys/bus/w1/devices/')


def start_w1():
    import os

    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')


def check_device_connection(device_dict) -> bool:
    for sensor_id in device_dict:
        if not Path(DEVICE_LOC, sensor_id).exists():
            logger.error(f'[THERMOCOUPLE] Device {sensor_id} not found at {DEVICE_LOC}.')
            return False
        else:
            logger.info(f'[THERMOCOUPLE] Device {sensor_id} found at {DEVICE_LOC}.')
    return True


def read_sensor_ROM(device_id):
    with Path(DEVICE_LOC, device_id, 'w1_slave').open('r') as f:
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
        temp_string = lines[1][equals_pos + 2 :]
        return float(temp_string) / 1000.0
    else:
        return None


def thermocouple_controller() -> tuple[int, str, dict | None]:
    """
    Reads thermocouples, saves data, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
    """
    logger.info('[THERMOCOUPLE]  --- Starting Thermocouple Controller ---')
    metadata_dict = None
    temp_data = {}

    try:
        logger.info('[THERMOCOUPLE]  Checking sensor connections ...')
        measurement_timestamp = datetime.datetime.now()
        if not check_device_connection(THERMOCOUPLE_IDS):
            logger.info('[THERMOCOUPLE]  Attempting to connect sensors manually.')
            start_w1()
            time.sleep(0.5)
            if not check_device_connection(THERMOCOUPLE_IDS):
                metadata_dict = {
                    'type': 'temperature',
                    'timestamp_iso': measurement_timestamp.isoformat(),
                    'data': None,
                    'error_flag': True,
                    'error_message': '[THERMOCOUPLE] [ERROR] Sensor(s) not found.',
                }
                return (1, '[THERMOCOUPLE] [ERROR] Sensor(s) not found.', None)

        logger.info('[THERMOCOUPLE]  Taking temperature measurements ...')

        error = False
        error_message = 'Error reading temperature from:'
        for sensor_id, sensor_name in THERMOCOUPLE_IDS.items():
            temperature = read_temp(sensor_id)
            if temperature is None:
                error = True
                ''.join(error_message, f'{sensor_name} ({sensor_id})')
                logger.error(f'[THERMOCOUPLE] Error reading temperature from: {sensor_name} ({sensor_id})')
            temp_data[sensor_name] = temperature

        if error:
            metadata = {
                'type': 'temperature',
                'timestamp_iso': measurement_timestamp.isoformat(),
                'data': None,
                'error_flag': True,
                'error_message': f'[THERMOCOUPLE] [ERROR] {error_message}',
            }
            return (1, f'[THERMOCOUPLE] [ERROR] {error_message}', None)

        logger.info(f'[THERMOCOUPLE] Measured: {temp_data}')

        metadata_dict = {
            'type': 'temperature',
            'timestamp_iso': measurement_timestamp.isoformat(),
            'data': temp_data,
            'error_flag': False,
            'error_message': None,
        }
        return (0, '[THERMOCOUPLE] [INFO] Data captured successfully.', metadata_dict)

    except Exception as e:
        logger.error(f'[THERMOCOUPLE] Unexpected error: {e}')
        metadata = {
            'type': 'temperature',
            'timestamp_iso': measurement_timestamp.isoformat(),
            'data': None,
            'error_flag': True,
            'error_message': f'Unexpected error: {e}',
        }
        return (1, f'[THERMOCOUPLE] [ERROR] Failed during operation: {e}', metadata)
    finally:
        logger.info('[THERMOCOUPLE]  --- Thermocouple Controller Done ---')
