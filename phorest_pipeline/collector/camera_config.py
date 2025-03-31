# process_pipeline/collector/camera_config.py
import configparser
from pathlib import Path

CONFIG_FILE = Path('camera_config.ini')


def load_config():
    """Loads configuration file."""
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(f'Configuration file not found: {CONFIG_FILE}')
    parser = configparser.ConfigParser()
    parser.read(CONFIG_FILE)
    return parser



# Load config once on import
try:
    settings = load_config()
    # Get parameters
    CAMERA_INDEX = settings.getint('Parameters', 'camera_index', fallback=1)
except (FileNotFoundError, ValueError, configparser.Error) as e:
    print(f'FATAL ERROR loading configuration: {e}')
    # In a real app, exit or use default fallbacks
    # For this example, make flags invalid
    settings = None
    CAMERA_INDEX = 0
