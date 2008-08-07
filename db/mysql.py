
from django.db import connection
from south.db import generic

class DatabaseOperations(generic.DatabaseOperations):

    """
    MySQL implementation of database operations.
    """

    types = generic.DatabaseOperations.types
    types['datetime'] = "datetime"

    def rename_column(self, table_name, old, new):
        if old == new:
            return []
        
        qn = connection.ops.quote_name
        
        params = (qn(table_namee), qn(old), qn(new))
        return ['ALTER TABLE %s CHANGE COLUMN %s %s;' % params]


    def rename_table(self, old_table_name, table_name):
        """
        Renames the table 'old_table_name' to 'table_name'.
        """
        if old_table_name == table_name:
            # No Operation
            return
        qn = connection.ops.quote_name
        params = (qn(old_table_name), qn(table_name))
        self.execute('RENAME TABLE %s TO %s;' % params)