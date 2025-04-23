# src/process_pipeline/shared/config.py
import ast
import configparser
from pathlib import Path

CONFIG_FILE = Path('config.ini')


def load_config():
    """Loads configuration file."""
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(f'Configuration file not found: {CONFIG_FILE}')
    parser = configparser.ConfigParser()
    parser.read(CONFIG_FILE)
    return parser


def get_path(config, dir_name_key: str, fallback: str) -> Path:
    """Gets the full path from a key in config."""
    new_dir = Path(config.get('Paths', dir_name_key, fallback=fallback))
    new_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    return new_dir


def get_flag_path(config, flag_name_key: str) -> Path:
    """Gets the full path for a flag file."""
    flag_dir = get_path(config, 'flag_dir', 'flags')
    flag_filename = config.get('Flags', flag_name_key)
    if not flag_filename:
        raise ValueError(f"Flag key '{flag_name_key}' not found in config [Flags]")
    return Path(flag_dir, flag_filename)


# Load config once on import
try:
    settings = load_config()  # Make sure load_config loads 'config.ini'

    # --- Flags ---
    DATA_READY_FLAG = get_flag_path(settings, 'data_ready')
    RESULTS_READY_FLAG = get_flag_path(settings, 'results_ready')

    # --- Paths ---
    DATA_DIR = Path(settings.get('Paths', 'data_dir', fallback='data'))
    RESULTS_DIR = Path(settings.get('Paths', 'results_dir', fallback='results'))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Timing ---
    COLLECTOR_INTERVAL = settings.getint('Timing', 'collector_interval_seconds', fallback=300)
    POLL_INTERVAL = settings.getint('Timing', 'poll_interval_seconds', fallback=2)
    RETRY_DELAY = settings.getint('Timing', 'collector_retry_delay_seconds', fallback=2)
    ENABLE_COMPRESSOR = settings.getboolean('Timing', 'enable_image_compression', fallback=False)
    COMPRESSOR_INTERVAL = settings.getint('Timing', 'compress_interval_seconds', fallback=60)

    # --- Retries ---
    FAILURE_LIMIT = settings.getint('Retries', 'collector_failure_limit', fallback=5)

    # --- Buffer ---
    IMAGE_BUFFER_SIZE = settings.getint('Buffer', 'image_buffer_size', fallback=10)

    # --- Component Availability ---
    # Use getboolean for true/false values
    ENABLE_CAMERA = settings.getboolean('Camera', 'camera', fallback=True)
    ENABLE_THERMOCOUPLE = settings.getboolean('Temperature', 'thermocouple', fallback=True)
    ENABLE_BRIGHTFIELD = settings.getboolean('Brightfield', 'brightfield', fallback=False)

    # --- Camera Settings ---
    CAMERA_INDEX = settings.getint('Camera', 'camera_id', fallback=1)
    CAMERA_EXPOSURE = settings.getint('Camera', 'camera_exposure', fallback=150)
    CAMERA_BRIGHTNESS = settings.getint('Camera', 'camera_brightness', fallback=128)
    CAMERA_CONTRAST = settings.getint('Camera', 'camera_contrast', fallback=32)

    # --- Temperature Settings ---
    # Parse the list string using ast.literal_eval
    tc_id_str = settings.get('Temperature', 'thermocouple_id', fallback='[]')
    try:
        THERMOCOUPLE_IDS = ast.literal_eval(tc_id_str)
        if not isinstance(THERMOCOUPLE_IDS, list):
            print(
                f"[CONFIG] [WARN] 'thermocouple_id' in config is not a list: {tc_id_str}. Using default []."
            )
            THERMOCOUPLE_IDS = []
    except (ValueError, SyntaxError) as e:
        print(
            f"[CONFIG] [WARN] Could not parse 'thermocouple_id': {tc_id_str}. Error: {e}. Using default []."
        )
        THERMOCOUPLE_IDS = []  # Default to empty list on parsing error

    # --- Brightfield Settings ---
    # Example reading brightfield specific camera ID
    BRIGHTFIELD_CAMERA_INDEX = settings.getint(
        'Brightfield', 'camera_id', fallback=1
    )  # Read specific ID if needed

except (FileNotFoundError, ValueError, configparser.Error) as e:
    print(f'FATAL ERROR loading/parsing configuration: {e}')
    # Set default fallbacks for critical components
    settings = None

    DATA_READY_FLAG = Path('ERROR_data_ready.flag')
    RESULTS_READY_FLAG = Path('ERROR_results_ready.flag')

    DATA_DIR = Path('ERROR_data')
    RESULTS_DIR = Path('ERROR_results')

    COLLECTOR_INTERVAL = 300
    POLL_INTERVAL = 2
    RETRY_DELAY = 2

    FAILURE_LIMIT = 5
    IMAGE_BUFFER_SIZE = 10

    # Default availability flags on error
    ENABLE_CAMERA = False
    ENABLE_THERMOCOUPLE = False
    ENABLE_BRIGHTFIELD = False

    # Default settings on error
    CAMERA_INDEX = 0
    THERMOCOUPLE_IDS = []
    BRIGHTFIELD_CAMERA_INDEX = 0
    # sys.exit(f"Configuration error: {e}") # Consider making errors fatal
