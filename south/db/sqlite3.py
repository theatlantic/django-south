import inspect
import re

from django.db import connection
from django.db.models import ForeignKey

from south.db import generic
from django.core.management.commands import inspectdb

qn = connection.ops.quote_name
    
class DatabaseOperations(generic.DatabaseOperations):

    """
    SQLite3 implementation of database operations.
    """
    
    backend_name = "sqlite3"

    # SQLite ignores foreign key constraints. I wish I could.
    supports_foreign_keys = False
    
    def __init__(self):
        super(DatabaseOperations, self).__init__()

    # You can't add UNIQUE columns with an ALTER TABLE.
    def add_column(self, table_name, name, field, *args, **kwds):
        # Run ALTER TABLE with no unique column
        unique, field._unique, field.db_index = field.unique, False, False
        # If it's not nullable, and has no default, raise an error (SQLite is picky)
        if (not field.null and 
            (not field.has_default() or field.get_default() is None) and
            not field.empty_strings_allowed):
            raise ValueError("You cannot add a null=False column without a default value.")
        # Don't try and drop the default, it'll fail
        kwds['keep_default'] = True
        generic.DatabaseOperations.add_column(self, table_name, name, field, *args, **kwds)
        # If it _was_ unique, make an index on it.
        if unique:
            self.create_index(table_name, [field.column], unique=True)
    
    def _remake_table(self, table_name, renames={}, deleted=[], altered={}):
        """
        Given a table and three sets of changes (renames, deletes, alters),
        recreates it with the modified schema.
        """
        # Temporary table's name
        temp_name = "_south_new_" + table_name
        
        # Work out the (possibly new) definitions of each column
        definitions = {}
        cursor = connection.cursor()
        for column_info in connection.introspection.get_table_description(cursor, table_name):
            name = column_info[0]
            type = column_info[1]
            # Deal with a rename
            if name in renames:
                name = renames[name]
            # Add to the defs
            definitions[name] = type
        # Alright, Make the table
        self.execute("CREATE TABLE %s (%s)" % (
            qn(temp_name),
            ", ".join(["%s %s" % (qn(cname), ctype) for cname, ctype in definitions.items()]),
        ))
        # Copy over the data
        self._copy_data(table_name, temp_name, renames)
        # Delete the old table, move our new one over it
        self.delete_table(table_name)
        self.rename_table(temp_name)
    
    def _copy_data(self, src, dst, field_renames={}):
        "Used to copy data into a new table"
        # Make a list of all the fields to select
        cursor = connection.cursor()
        q_fields = [column_info[0] for column_info in connection.introspection.get_table_description(cursor, table_name)]
        # Make sure renames are done correctly
        for old, new in field_renames.items():
            q_fields[q_fields.index(new)] = "%s AS %s" % (old, qn(new))
        # Copy over the data
        self.execute("INSERT INTO %s SELECT %s FROM %s;" % (
            qn(dst),
            ', '.join(q_fields),
            qn(src),
        ))
    
    def alter_column(self, table_name, name, field, explicit_name=True):
        raise NotImplementedError

    def delete_column(self, table_name, column_name):
        raise NotImplementedError
    
    def rename_column(self, table_name, old, new):
        """
        Renames a column from one name to another.
        """
        self._remake_table(table_name, renames={old: new})
    
    # Nor unique creation
    def create_unique(self, table_name, columns):
        """
        Not supported under SQLite.
        """
        print "   ! WARNING: SQLite does not support adding unique constraints. Ignored."
    
    # Nor unique deletion
    def delete_unique(self, table_name, columns):
        """
        Not supported under SQLite.
        """
        print "   ! WARNING: SQLite does not support removing unique constraints. Ignored."
    
    # No cascades on deletes
    def delete_table(self, table_name, cascade=True):
        generic.DatabaseOperations.delete_table(self, table_name, False)

    
