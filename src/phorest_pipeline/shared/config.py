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


def get_flag_path(config, flag_name_key: str) -> Path:
    """Gets the full path for a flag file."""
    flag_dir = Path(config.get('Paths', 'flag_dir', fallback='flags'))
    flag_filename = config.get('Flags', flag_name_key)
    if not flag_filename:
        raise ValueError(f"Flag key '{flag_name_key}' not found in config [Flags]")
    flag_dir.mkdir(parents=True, exist_ok=True)  # Ensure flag directory exists
    return Path(flag_dir, flag_filename)


# Load config once on import
try:
    settings = load_config()
    # Pre-calculate flag paths
    DATA_READY_FLAG = get_flag_path(settings, 'data_ready')
    RESULTS_READY_FLAG = get_flag_path(settings, 'results_ready')
    # Get timing
    COLLECTOR_INTERVAL = settings.getint('Timing', 'collector_interval_seconds', fallback=300)
    POLL_INTERVAL = settings.getint('Timing', 'poll_interval_seconds', fallback=2)

except (FileNotFoundError, ValueError, configparser.Error) as e:
    print(f'FATAL ERROR loading configuration: {e}')
    # In a real app, exit or use default fallbacks
    # For this example, make flags invalid
    settings = None
    DATA_READY_FLAG = Path('ERROR_data_ready.flag')
    RESULTS_READY_FLAG = Path('ERROR_results_ready.flag')
    COLLECTOR_INTERVAL = 300
    POLL_INTERVAL = 2
