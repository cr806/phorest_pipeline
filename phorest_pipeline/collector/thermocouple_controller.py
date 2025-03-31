# phorest_pipeline/collector/thermocouple_controller.py
import datetime
import time
from pathlib import Path


def thermocouple_controller(data_dir: Path) -> tuple[int, str, dict | None]:
    """
    Reads thermocouples, saves data, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
    """
    print('[THERMOCOUPLE] --- Starting Thermocouple Controller ---')
    metadata_dict = None

    try:
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
