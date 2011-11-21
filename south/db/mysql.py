# MySQL-specific implementations for south
# Original author: Andrew Godwin
# Patches by: F. Gabriel Gosselin <gabrielNOSPAM@evidens.ca>
#             aarranz

from django.db import connection
from django.conf import settings
from south.db import generic

from south.logger import get_logger

def delete_column_constraints(func):
    """
    Decorates column operation functions for MySQL.
    Deletes the constraints from the database and clears local cache.
    """
    def _column_rm(self, table_name, column_name, *args, **opts):
        try:
            self.delete_foreign_key(table_name, column_name)
        except ValueError:
            pass # If no foreign key on column, OK because it checks first

        return func(self, table_name, column_name, *args, **opts)
    return _column_rm

class DatabaseOperations(generic.DatabaseOperations):
    """
    MySQL implementation of database operations.

    MySQL has no DDL transaction support This can confuse people when they ask
    how to roll back - hence the dry runs, etc., found in the migration code.
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

    geom_types = ['geometry', 'point', 'linestring', 'polygon']
    text_types = ['text', 'blob',]

    def __init__(self, db_alias):
        self._constraint_references = {}
        self._reverse_cache = {}
        super(DatabaseOperations, self).__init__(db_alias)

    def _is_valid_cache(self, db_name, table_name):
        cache = self._constraint_cache
        # we cache the whole db so if there are any tables table_name is valid
        return db_name in cache and cache[db_name].get(table_name, None) is not generic.INVALID

    def _fill_constraint_cache(self, db_name, table_name):
        # for MySQL grab all constraints for this database.  It's just as cheap as a single column.
        self._constraint_cache[db_name] = {}
        self._constraint_cache[db_name][table_name] = {}
        self._reverse_cache[db_name] = {}
        self._constraint_references[db_name] = {}

        name_query = """
            SELECT kc.`constraint_name`, kc.`column_name`, kc.`table_name`,
                kc.`referenced_table_name`, kc.`referenced_column_name`
            FROM information_schema.key_column_usage AS kc
            WHERE
                kc.table_schema = %s
        """
        rows = self.execute(name_query, [db_name])
        if not rows:
            return
        cnames = {}
        for constraint, column, table, ref_table, ref_column in rows:
            key = (table, constraint)
            cnames.setdefault(key, set())
            cnames[key].add((column, ref_table, ref_column))

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
            for column_set in cols:
                (column, ref_table, ref_column) = column_set
                self._constraint_cache[db_name][table].setdefault(column, set())
                if kind == 'FOREIGN KEY':
                    self._constraint_cache[db_name][table][column].add((kind,
                        constraint))
                    # Create constraint lookup, see constraint_references
                    self._constraint_references[db_name][(table,
                        constraint)] = (ref_table, ref_column)
                    # Create reverse table lookup, reverse_lookup
                    self._reverse_cache[db_name].setdefault(ref_table, {})
                    self._reverse_cache[db_name][ref_table].setdefault(ref_column,
                            set())
                    self._reverse_cache[db_name][ref_table][ref_column].add(
                            (constraint, table, column))
                else:
                    self._constraint_cache[db_name][table][column].add((kind,
                    constraint))

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

    @delete_column_constraints
    def delete_column(self, table_name, name):
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

    def _lookup_constraint_references(self, table_name, cname):
        """
        Provided an existing table and constraint, returns tuple of (foreign
        table, column)
        """
        db_name = self._get_setting('NAME')
        try:
            return self._constraint_references[db_name][(table_name, cname)]
        except KeyError:
            return None

    def _lookup_reverse_constraint(self, table_name, column_name=None):
        """Look for the column referenced by a foreign constraint"""
        db_name = self._get_setting('NAME')
        if self.dry_run:
            raise DryRunError("Cannot get constraints for columns.")

        if not self._is_valid_cache(db_name, table_name):
            # Piggy-back on lookup_constraint, ensures cache exists
            self.lookup_constraint(db_name, table_name)

        try:
            table = self._reverse_cache[db_name][table_name]
            if column_name == None:
                return table.items()
            else:
                return table[column_name]
        except KeyError, e:
            return []

    def _field_sanity(self, field):
        """
        This particular override stops us sending DEFAULTs for BLOB/TEXT columns.
        """
        #  MySQL does not support defaults for geometry columns also
        type = self._db_type_for_alter_column(field).lower()
        is_geom = True in [ type.find(t) > -1 for t in self.geom_types ]
        is_text = True in [ type.find(t) > -1 for t in self.text_types ]

        if is_geom or is_text:
            field._suppress_default = True
        return field

    def _alter_set_defaults(self, field, name, params, sqls):
        """
        MySQL does not support defaults on text or blob columns.
        """
        type = params['type']
        #  MySQL does not support defaults for geometry columns also
        is_geom = True in [ type.find(t) > -1 for t in self.geom_types ]
        is_text = True in [ type.find(t) > -1 for t in self.text_types ]
        if not is_geom and not is_text:
            super(DatabaseOperations, self)._alter_set_defaults(field, name, params, sqls)

class DryRunError(ValueError):
    pass
