import sys
import logging
from django.conf import settings

_logger = logging.getLogger("south")
_logger.addHandler( logging.StreamHandler(sys.stdout) ) # FIXME: NullHandler
_logger.setLevel(logging.DEBUG)

def getLogger():
    debug_on = getattr(settings, "SOUTH_DEBUG_ON", False)
    logging_file = getattr(settings, "SOUTH_LOGGING_FILE", False)
    
    if debug_on:
        if logging_file:
            _logger.addHandler( logging.FileHandler(logging_file) )
            _logger.setLevel(logging.DEBUG)
        else:
            raise IOError, "SOUTH_DEBUG_ON is True. You also need a SOUTH_LOGGING_FILE setting."
    return _logger
