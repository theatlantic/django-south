import os
import unittest
from django.conf import settings
from django.db import connection, models

from south.db import db

# 
# # Create a list of error classes from the various database libraries
# errors = []
# try:
#     from psycopg2 import ProgrammingError
#     errors.append(ProgrammingError)
# except ImportError:
#     pass
# errors = tuple(errors)

class TestLogger(unittest.TestCase):

    """
    Tests if the various logging functions.
    """

    # TODO: Test if DEBUG is False
    
    def setUp(self):
        db.debug = False
        db.clear_deferred_sql()
        settings.DEBUG = True

    def test_db_execute_logging_nofile(self):
        """ Does logging degrade nicely if no file.
        """
        db.create_table("test1", [('email_confirmed', models.BooleanField(default=False))])
        
    # def test_db_execute_logging_garbagefile(self):
    #     """ Does logging degrade nicely if garbage file.
    #     """
    #     settings.SOUTH_LOGGING_FILE = "garbage path"
    #     db.create_table("test2", [('email_confirmed', models.BooleanField(default=False))])
        
    def test_db_execute_logging_validfile(self):
        """ Does logging degrade nicely if valid file.
        """
        settings.SOUTH_LOGGING_FILE = os.path.join(
            os.path.dirname(__file__),
            "test.log",
        )
        db.create_table("test3", [('email_confirmed', models.BooleanField(default=False))])
        
