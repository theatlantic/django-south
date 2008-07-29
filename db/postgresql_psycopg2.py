
from django.db import connection
from south.db import generic

class DatabaseOperations(generic.DatabaseOperations):

    """
    PsycoPG2 implementation of database operations.
    """

    def rename_column(self, table_name, old, new):
        if old == new:
            return []
        qn = connection.ops.quote_name
        params = (qn(table_name), qn(old), qn(new))
        self.execute('ALTER TABLE %s RENAME COLUMN %s TO %s;' % params)