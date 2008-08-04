
from django.db import connection, transaction

class DatabaseOperations(object):

    """
    Generic SQL implementation of the DatabaseOperations.
    Some of this code comes from Django Evolution.
    """

    types = {
        "varchar": "VARCHAR",
        "text": "TEXT",
        "integer": "INT",
        "boolean": "BOOLEAN",
        "serial": "SERIAL",
        "datetime": "TIMESTAMP WITH TIME ZONE",
        "float": "DOUBLE PRECISION",
    }

    def __init__(self):
        self.debug = False


    def get_type(self, name, param=None):
        """
        Generic type-converting method, to smooth things over.
        """
        if name in ["text", "string"]:
            if param:
                return "%s(%s)" % (self.types['varchar'], param)
            else:
                return self.types['text']
        else:
            return self.types[name]


    def execute(self, sql, params=[]):
        """
        Executes the given SQL statement, with optional parameters.
        If the instance's debug attribute is True, prints out what it executes.
        """
        cursor = connection.cursor()
        if self.debug:
            print "   = %s" % sql, params
        return cursor.execute(sql, params)


    def get_column_value(self, column, name):
        """
        Gets a column's something value from either a list or dict.
        Useful for when both are passed into create_table in the column list.
        """
        defaults = {
            "type_param": 0,
            "unique": False,
            "null": True,
            "related_to": None,
            "default": None,
            "primary": False,
        }
        if isinstance(column, (list, tuple)):
            try:
                return column[{
                    "name": 0,
                    "type": 1,
                    "type_param": 2,
                    "unique": 3,
                    "null": 4,
                    "related_to": 5,
                    "default": 6,
                    "primary": 7,
                }[name]]
            except IndexError:
                return defaults[name]
        else:
            return column.get(name, defaults.get(name, None))


    def create_table(self, table_name, columns):
        """
        Creates the table 'table_name'. 'columns' is a list of columns
        in the same format used by add_column (but as a list - think of its
        positional arguments).
        """
        qn = connection.ops.quote_name
        defaults = tuple(self.get_column_value(column, "default") for column in columns)
        columns = [
            self.column_sql(
                column_name = self.get_column_value(column, "name"),
                type_name = self.get_column_value(column, "type"),
                type_param = self.get_column_value(column, "type_param"),
                unique = self.get_column_value(column, "unique"),
                null = self.get_column_value(column, "null"),
                related_to = self.get_column_value(column, "related_to"),
                default = self.get_column_value(column, "default"),
            )
            for column in columns
        ]
        sqlparams = tuple()
        for s, p in columns:
            sqlparams += p
        params = (
            qn(table_name),
            ", ".join([s for s,p in columns]),
        )
        self.execute('CREATE TABLE %s (%s);' % params, sqlparams)


    def rename_table(self, old_table_name, table_name):
        """
        Renames the table 'old_table_name' to 'table_name'.
        """
        if old_table_name == table_name:
            # No Operation
            return
        qn = connection.ops.quote_name
        params = (qn(old_table_name), qn(table_name))
        self.execute('ALTER TABLE %s RENAME TO %s;' % params)


    def delete_table(self, table_name):
        """
        Deletes the table 'table_name'.
        """
        qn = connection.ops.quote_name
        params = (qn(table_name), )
        self.execute('DROP TABLE %s;' % params)


    def add_column(self, table_name, name, type, type_param=None, unique=False, null=True, related_to=None, default=None, primary=False):
        """
        Adds the column 'column_name' to the table 'table_name'.
        The column will have type 'type_name', which is one of the generic
        types South offers, such as 'string' or 'integer'.
        
        @param table_name: The name of the table to add the column to
        @param column_name: The name of the column to add
        @param type_name: The (generic) name of this column's type
        @param type_param: An optional parameter to the type - e.g., its length
        @param unique: Whether this column has UNIQUE set. Defaults to False.
        @param null: If this column will be allowed to contain NULL values. Defaults to True.
        @param related_to: A tuple of (table_name, column_name) for the column this references if it is a ForeignKey.
        @param primary: If this is the primary key column
        """
        qn = connection.ops.quote_name
        sql, sqlparams = self.column_sql(name, type, type_param, unique, null, related_to)
        params = (
            qn(table_name),
            sql,
        )
        sql = 'ALTER TABLE %s ADD COLUMN %s;' % params
        self.execute(sql, sqlparams)


    def column_sql(self, column_name, type_name, type_param=None, unique=False, null=True, related_to=None, default=None, primary=False):
        """
        Creates the SQL snippet for a column. Used by add_column and add_table.
        """
        qn = connection.ops.quote_name
        no_default = (not default)
        if type_name == "serial":
            no_default = True
            null = False
        params = (
            qn(column_name),
            self.get_type(type_name, type_param),
            (unique and "UNIQUE " or "") + (null and "NULL" or ""),
            related_to and ("REFERENCES %s (%s) %s" % (
                related_to[0],  # Table name
                related_to[1],  # Column name
                connection.ops.deferrable_sql(), # Django knows this
            )) or "",
            not no_default and "DEFAULT %s" or "",
        )
        sqlparams = not no_default and (default,) or tuple() 
        return '%s %s %s %s %s' % params, sqlparams


    def delete_column(self, table_name, column_name):
        """
        Deletes the column 'column_name' from the table 'table_name'.
        """
        qn = connection.ops.quote_name
        params = (qn(mtable_name), qn(column_name))
        return ['ALTER TABLE %s DROP COLUMN %s CASCADE;' % params]


    def rename_column(self, table_name, old, new):
        """
        Renames the column 'old' from the table 'table_name' to 'new'.
        """
        raise NotImplementedError("rename_column has no generic SQL syntax")


    def commit_transaction(self):
        """
        Commits the current transaction.
        """
        transaction.commit()


    def rollback_transaction(self):
        """
        Rolls back the current transaction.
        """
        transaction.rollback()