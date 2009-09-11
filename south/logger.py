import sys
import logging
from django.conf import settings

logging_file = None
if hasattr(settings, "SOUTH_LOGGING_FILE"):
    logging_file = settings.SOUTH_LOGGING_FILE

logger = logging.getLogger("south")
logger.addHandler( logging.StreamHandler(sys.stdout) )
logger.setLevel(logging.DEBUG)
