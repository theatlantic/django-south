import unittest

from south.db import db
from django.db import connection, models

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
        db.clear_deferred_sql()

    def test_create(self):
        """
        Test creation and deletion of tables.
        """
        cursor = connection.cursor()
        # It needs to take at least 2 args
        self.assertRaises(TypeError, db.create_table)
        self.assertRaises(TypeError, db.create_table, "test1")
        # Empty tables (i.e. no columns) are not fine, so make at least 1
        db.create_table("test1", [('email_confirmed', models.BooleanField(default=False))])
        db.start_transaction()
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
        db.start_transaction()
        # Remove the table
        db.drop_table("test1")
        # Make sure it went
        try:
            cursor.execute("SELECT * FROM test1")
            self.fail("Just-deleted table could be selected!")
        except:
            pass
        # Clear the dirty transaction
        db.rollback_transaction()
        db.start_transaction()
        # Try deleting a nonexistent one
        try:
            db.delete_table("nottheretest1")
            self.fail("Non-existent table could be deleted!")
        except:
            pass
        db.rollback_transaction()
    
    def test_foreign_keys(self):
        """
        Tests foreign key creation, especially uppercase (see #61)
        """
        Test = db.mock_model(model_name='Test', db_table='test5a',
                             db_tablespace='', pk_field_name='ID',
                             pk_field_type=models.AutoField, pk_field_args=[])
        cursor = connection.cursor()
        db.start_transaction()
        db.create_table("test5a", [('ID', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True))])
        db.create_table("test5b", [
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('UNIQUE', models.ForeignKey(Test)),
        ])
        db.execute_deferred_sql()
        db.rollback_transaction()
    
    def test_rename(self):
        """
        Test column renaming
        """
        cursor = connection.cursor()
        db.create_table("test_rn", [('spam', models.BooleanField(default=False))])
        db.start_transaction()
        # Make sure we can select the column
        cursor.execute("SELECT spam FROM test_rn")
        # Rename it
        db.rename_column("test_rn", "spam", "eggs")
        cursor.execute("SELECT eggs FROM test_rn")
        try:
            cursor.execute("SELECT spam FROM test_rn")
            self.fail("Just-renamed column could be selected!")
        except:
            pass
        db.rollback_transaction()
        db.delete_table("test_rn")
    
    def test_dry_rename(self):
        """
        Test column renaming while --dry-run is turned on (should do nothing)
        See ticket #65
        """
        cursor = connection.cursor()
        db.create_table("test_drn", [('spam', models.BooleanField(default=False))])
        db.start_transaction()
        # Make sure we can select the column
        cursor.execute("SELECT spam FROM test_drn")
        # Rename it
        db.dry_run = True
        db.rename_column("test_drn", "spam", "eggs")
        db.dry_run = False
        cursor.execute("SELECT spam FROM test_drn")
        try:
            cursor.execute("SELECT eggs FROM test_drn")
            self.fail("Dry-renamed new column could be selected!")
        except:
            pass
        db.rollback_transaction()
        db.delete_table("test_drn")
    
    def test_table_rename(self):
        """
        Test column renaming
        """
        cursor = connection.cursor()
        db.create_table("testtr", [('spam', models.BooleanField(default=False))])
        db.start_transaction()
        # Make sure we can select the column
        cursor.execute("SELECT spam FROM testtr")
        # Rename it
        db.rename_table("testtr", "testtr2")
        cursor.execute("SELECT spam FROM testtr2")
        try:
            cursor.execute("SELECT spam FROM testtr")
            self.fail("Just-renamed column could be selected!")
        except:
            pass
        db.rollback_transaction()
        db.delete_table("testtr2")
    
    def test_index(self):
        """
        Test the index operations
        """
        db.create_table("test3", [
            ('SELECT', models.BooleanField(default=False)),
            ('eggs', models.IntegerField(unique=True)),
        ])
        db.execute_deferred_sql()
        db.start_transaction()
        # Add an index on that column
        db.create_index("test3", ["SELECT"])
        # Add another index on two columns
        db.create_index("test3", ["SELECT", "eggs"])
        # Delete them both
        db.delete_index("test3", ["SELECT"])
        db.delete_index("test3", ["SELECT", "eggs"])
        # Delete the unique index
        db.delete_index("test3", ["eggs"])
        db.rollback_transaction()
        db.delete_table("test3")
    
    def test_primary_key(self):
        """
        Test the primary key operations
        """
        db.create_table("test_pk", [
            ('id', models.IntegerField(primary_key=True)),
            ('new_pkey', models.IntegerField()),
            ('eggs', models.IntegerField(unique=True)),
        ])
        db.execute_deferred_sql()
        db.start_transaction()
        # Remove the default primary key, and make eggs it
        db.drop_primary_key("test_pk")
        db.create_primary_key("test_pk", "new_pkey")
        # Try inserting a now-valid row pair
        db.execute("INSERT INTO test_pk (id, new_pkey, eggs) VALUES (1, 2, 3), (1, 3, 4)")
        db.rollback_transaction()
        db.delete_table("test_pk")
    
    def test_alter(self):
        """
        Test altering columns/tables
        """
        db.create_table("test4", [
            ('spam', models.BooleanField(default=False)),
            ('eggs', models.IntegerField()),
        ])
        db.start_transaction()
        # Add a column
        db.add_column("test4", "add1", models.IntegerField(default=3), keep_default=False)
        # Add a FK with keep_default=False (#69)
        User = db.mock_model(model_name='User', db_table='auth_user', db_tablespace='', pk_field_name='id', pk_field_type=models.AutoField, pk_field_args=[], pk_field_kwargs={})
        db.add_column("test4", "user", models.ForeignKey(User), keep_default=False)
        db.delete_column("test4", "add1")
        
        db.rollback_transaction()
        db.delete_table("test4")
    
    def test_unique(self):
        """
        Tests creating/deleting unique constraints.
        """
        db.create_table("test_unique", [
            ('spam', models.BooleanField(default=False)),
            ('eggs', models.IntegerField()),
        ])
        # Add a constraint
        db.create_unique("test_unique", ["spam"])
        db.delete_unique("test_unique", ["spam"])
        db.create_unique("test_unique", ["spam"])
        db.start_transaction()
        # Test it works
        db.execute("INSERT INTO test_unique (spam, eggs) VALUES (true, 0), (false, 1)")
        try:
            db.execute("INSERT INTO test_unique (spam, eggs) VALUES (true, 2)")
        except:
            db.rollback_transaction()
        else:
            self.fail("Could insert non-unique item.")
        # Drop that, add one only on eggs
        db.delete_unique("test_unique", ["spam"])
        db.execute("DELETE FROM test_unique")
        db.create_unique("test_unique", ["eggs"])
        db.start_transaction()
        # Test similarly
        db.execute("INSERT INTO test_unique (spam, eggs) VALUES (true, 0), (false, 1)")
        try:
            db.execute("INSERT INTO test_unique (spam, eggs) VALUES (true, 1)")
        except:
            db.rollback_transaction()
        else:
            self.fail("Could insert non-unique item.")
        # Drop those, test combined constraints
        db.delete_unique("test_unique", ["eggs"])
        db.execute("DELETE FROM test_unique")
        db.create_unique("test_unique", ["spam", "eggs"])
        db.start_transaction()
        # Test similarly
        db.execute("INSERT INTO test_unique (spam, eggs) VALUES (true, 0), (false, 1), (true, 1)")
        try:
            db.execute("INSERT INTO test_unique (spam, eggs) VALUES (true, 0)")
        except:
            db.rollback_transaction()
        else:
            self.fail("Could insert non-unique pair.")
        
        