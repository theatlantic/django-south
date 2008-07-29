import unittest

from south.db import db
from django.db import connection

# Create a list of error classes from the various database libraries
errors = []
try:
    from psycopg2 import ProgrammingError
    errors.append(ProgrammingError)
except ImportError:
    pass
errors = tuple(errors)

class TestOperations(unittest.TestCase):

    """
    Tests if the various DB abstraction calls work.
    Can only test a limited amount due to DB differences.
    """

    def setUp(self):
        db.debug = False

    def test_create(self):
        """
        Test creation and deletion of tables.
        """
        cursor = connection.cursor()
        # It needs to take at least 2 args
        self.assertRaises(TypeError, db.create_table)
        self.assertRaises(TypeError, db.create_table, "test1")
        # Empty tables (i.e. no columns) are fine
        db.create_table("test1", [])
        db.commit_transaction()
        # And should exist
        cursor.execute("SELECT * FROM test1")
        # Make sure we can't do the same query on an empty table
        try:
            cursor.execute("SELECT * FROM nottheretest1")
            self.fail("Non-existent table could be selected!")
        except:
            pass
        # Clear the dirty transaction
        db.rollback_transaction()
        # Remove the table
        db.delete_table("test1")
        # Make sure it went
        try:
            cursor.execute("SELECT * FROM test1")
            self.fail("Just-deleted table could be selected!")
        except:
            pass
        # Clear the dirty transaction
        db.rollback_transaction()
        # Try deleting a nonexistent one
        try:
            db.delete_table("nottheretest1")
            self.fail("Non-existent table could be deleted!")
        except:
            pass