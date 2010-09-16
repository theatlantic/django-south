
from django.db import connection
from django.conf import settings
from south.db import generic

class DatabaseOperations(generic.DatabaseOperations):

    """
    MySQL implementation of database operations.
    
    MySQL is an 'interesting' database; it has no DDL transaction support,
    among other things. This can confuse people when they ask how they can
    roll back - hence the dry runs, etc., found in the migration code.
    Alex agrees, and Alex is always right.
    [19:06] <Alex_Gaynor> Also, I want to restate once again that MySQL is a special database
    
    (Still, if you want a key-value store with relational tendancies, go MySQL!)
    """
    
    backend_name = "mysql"
    alter_string_set_type = ''
    alter_string_set_null = 'MODIFY %(column)s %(type)s NULL;'
    alter_string_drop_null = 'MODIFY %(column)s %(type)s NOT NULL;'
    drop_index_string = 'DROP INDEX %(index_name)s ON %(table_name)s'
    delete_primary_key_sql = "ALTER TABLE %(table)s DROP PRIMARY KEY"
    delete_foreign_key_sql = "ALTER TABLE %(table)s DROP FOREIGN KEY %(constraint)s"
    allows_combined_alters = False
    has_ddl_transactions = False
    has_check_constraints = False
    delete_unique_sql = "ALTER TABLE %s DROP INDEX %s"

    def _is_valid_cache(self, db_name, table_name):
        cache = self._constraint_cache
        # we cache the whole db so if there are any tables table_name is valid
        return db_name in cache and cache[db_name].get(table_name, None) is not generic.INVALID

    def _fill_constraint_cache(self, db_name, table_name):
        # for MySQL grab all constraints for this database.  It's just as cheap as a single column.
        self._constraint_cache[db_name] = {}
        self._constraint_cache[db_name][table_name] = {}

        name_query = """
            SELECT kc.constraint_name, kc.column_name, kc.table_name
            FROM information_schema.key_column_usage AS kc
            WHERE
                kc.table_schema = %s AND
                kc.table_catalog IS NULL
        """
        rows = self.execute(name_query, [db_name])
        if not rows:
            return
        cnames = {}
        for constraint, column, table in rows:
            key = (table, constraint)
            cnames.setdefault(key, set())
            cnames[key].add(column)

        type_query = """
            SELECT c.constraint_name, c.table_name, c.constraint_type
            FROM information_schema.table_constraints AS c
            WHERE
                c.table_schema = %s
        """
        rows = self.execute(type_query, [db_name])
        for constraint, table, kind in rows:
            key = (table, constraint)
            self._constraint_cache[db_name].setdefault(table, {})
            try:
                cols = cnames[key]
            except KeyError:
                cols = set()
            for column in cols:
                self._constraint_cache[db_name][table].setdefault(column, set())
                self._constraint_cache[db_name][table][column].add((kind, constraint))


    def connection_init(self):
        """
        Run before any SQL to let database-specific config be sent as a command,
        e.g. which storage engine (MySQL) or transaction serialisability level.
        """
        cursor = self._get_connection().cursor()
        if self._has_setting('STORAGE_ENGINE') and self._get_setting('STORAGE_ENGINE'):
            cursor.execute("SET storage_engine=%s;" % self._get_setting('STORAGE_ENGINE'))
        # Turn off foreign key checks, and turn them back on at the end
        cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
        self.deferred_sql.append("SET FOREIGN_KEY_CHECKS=1;")

    @generic.copy_column_constraints
    @generic.delete_column_constraints
    def rename_column(self, table_name, old, new):
        if old == new or self.dry_run:
            return []
        
        rows = [x for x in self.execute('DESCRIBE %s' % (self.quote_name(table_name),)) if x[0] == old]
        
        if not rows:
            raise ValueError("No column '%s' in '%s'." % (old, table_name))
        
        params = (
            self.quote_name(table_name),
            self.quote_name(old),
            self.quote_name(new),
            rows[0][1],
            rows[0][2] == "YES" and "NULL" or "NOT NULL",
            rows[0][4] and "DEFAULT " or "",
            rows[0][4] and "%s" or "",
            rows[0][5] or "",
        )
        
        sql = 'ALTER TABLE %s CHANGE COLUMN %s %s %s %s %s %s %s;' % params
        
        if rows[0][4]:
            self.execute(sql, (rows[0][4],))
        else:
            self.execute(sql)

    @generic.delete_column_constraints
    def delete_column(self, table_name, name):
        db_name = self._get_setting('NAME')

        # See if there is a foreign key on this column
        result = 0
        for kind, cname in self.lookup_constraint(db_name, table_name, name):
            if kind == 'FOREIGN_KEY':
                result += 1
                fkey_name = cname
        if result:
            assert result == 1 # We should only have one result, otherwise there's Issues
            cursor = self._get_connection().cursor()
            drop_query = "ALTER TABLE %s DROP FOREIGN KEY %s"
            cursor.execute(drop_query % (self.quote_name(table_name), self.quote_name(fkey_name)))

        super(DatabaseOperations, self).delete_column(table_name, name)

    @generic.invalidate_table_constraints
    def rename_table(self, old_table_name, table_name):
        """
        Renames the table 'old_table_name' to 'table_name'.
        """
        if old_table_name == table_name:
            # No Operation
            return
        params = (self.quote_name(old_table_name), self.quote_name(table_name))
        self.execute('RENAME TABLE %s TO %s;' % params)

    def _field_sanity(self, field):
        """
        This particular override stops us sending DEFAULTs for BLOB/TEXT columns.
        """
        if self._db_type_for_alter_column(field).upper() in ["BLOB", "TEXT", "LONGTEXT"]:
            field._suppress_default = True
        return field
    
    
    def _alter_set_defaults(self, field, name, params, sqls):
        """
        MySQL does not support defaults on text or blob columns.
        """
        type = params['type']
        if not (type.endswith('text') or type.endswith('blob')):
            super(DatabaseOperations, self)._alter_set_defaults(field, name, params, sqls)
