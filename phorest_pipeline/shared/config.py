# src/process_pipeline/shared/config.py
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
    settings = load_config()
    # Pre-calculate flag paths
    DATA_READY_FLAG = get_flag_path(settings, 'data_ready')
    RESULTS_READY_FLAG = get_flag_path(settings, 'results_ready')
    # Get paths
    DATA_DIR = get_path(settings, 'camera_dir', 'data')
    # Get timing
    COLLECTOR_INTERVAL = settings.getint('Timing', 'collector_interval_seconds', fallback=300)
    POLL_INTERVAL = settings.getint('Timing', 'poll_interval_seconds', fallback=2)
    FAILURE_LIMIT = settings.getint('Retries', 'collector_failure_limit', fallback=5)
    RETRY_DELAY = settings.getint("Retries", "collector_retry_delay_seconds", fallback=3)
    # Get Buffer Size
    IMAGE_BUFFER_SIZE = settings.getint('Buffer', 'image_buffer_size', fallback=10)
except (FileNotFoundError, ValueError, configparser.Error) as e:
    print(f'FATAL ERROR loading configuration: {e}')
    # In a real app, exit or use default fallbacks
    # For this example, make flags invalid
    settings = None
    DATA_READY_FLAG = Path('ERROR_data_ready.flag')
    RESULTS_READY_FLAG = Path('ERROR_results_ready.flag')
    DATA_DIR = Path('ERROR_data_path')
    COLLECTOR_INTERVAL = 300
    POLL_INTERVAL = 2
    FAILURE_LIMIT = 5
    RETRY_DELAY = 3
    IMAGE_BUFFER_SIZE = 10
    # sys.exit(f"Configuration error: {e}") # Uncomment to make config errors fatal
