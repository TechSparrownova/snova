VERSION = "5.18.0"
PROJECT_NAME = "saps-snova"
SAPS_VERSION = None
current_path = None
updated_path = None
LOG_BUFFER = []


def set_saps_version(snova_path="."):
	from .utils.app import get_current_saps_version

	global SAPS_VERSION
	if not SAPS_VERSION:
		SAPS_VERSION = get_current_saps_version(snova_path=snova_path)
