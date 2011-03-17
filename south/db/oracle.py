import os.path
import sys
import re
import cx_Oracle


from django.db import connection, models
from django.db.backends.util import truncate_name
from django.core.management.color import no_style
from django.db.backends.oracle.base import get_sequence_name
from django.db.models.fields import NOT_PROVIDED
from django.db.utils import DatabaseError
from south.db import generic

print >> sys.stderr, " ! WARNING: South's Oracle support is still alpha."
print >> sys.stderr, " !          Be wary of possible bugs."

class DatabaseOperations(generic.DatabaseOperations):    
    """
    Oracle implementation of database operations.    
    """
    backend_name = 'oracle'

    alter_string_set_type =     'ALTER TABLE %(table_name)s MODIFY %(column)s %(type)s %(nullity)s;'
    alter_string_set_default =  'ALTER TABLE %(table_name)s MODIFY %(column)s DEFAULT %(default)s;'
    add_column_string =         'ALTER TABLE %s ADD %s;'
    delete_column_string =      'ALTER TABLE %s DROP COLUMN %s;'

    allows_combined_alters = False
    
    constraits_dict = {
        'PRIMARY KEY': 'P',
        'UNIQUE': 'U',
        'CHECK': 'C',
        'REFERENCES': 'R'
    }

    def adj_column_sql(self, col):
        col = re.sub('(?P<constr>CHECK \(.*\))(?P<any>.*)(?P<default>DEFAULT [0|1])', 
                     lambda mo: '%s %s%s'%(mo.group('default'), mo.group('constr'), mo.group('any')), col) #syntax fix for boolean field only
        col = re.sub('(?P<not_null>(NOT )?NULL) (?P<misc>(.* )?)(?P<default>DEFAULT.+)',
                     lambda mo: '%s %s %s'%(mo.group('default'),mo.group('not_null'),mo.group('misc') or ''), col) #fix order of NULL/NOT NULL and DEFAULT
        return col

    def check_meta(self, table_name):
        return table_name in [ m._meta.db_table for m in models.get_models() ] #caching provided by Django

    @generic.invalidate_table_constraints
    def create_table(self, table_name, fields): 
        qn = self.quote_name(table_name)
        columns = []
        autoinc_sql = ''

        for field_name, field in fields:
            col = self.column_sql(table_name, field_name, field)
            if not col:
                continue
            col = self.adj_column_sql(col)

            columns.append(col)
            if isinstance(field, models.AutoField):
                autoinc_sql = connection.ops.autoinc_sql(table_name, field_name)

        sql = 'CREATE TABLE %s (%s);' % (qn, ', '.join([col for col in columns]))
        self.execute(sql)
        if autoinc_sql:
            self.execute(autoinc_sql[0])
            self.execute(autoinc_sql[1])

    @generic.invalidate_table_constraints
    def delete_table(self, table_name, cascade=True):
        qn = self.quote_name(table_name)

        if cascade:
            self.execute('DROP TABLE %s CASCADE CONSTRAINTS PURGE;' % qn)
        else:
            self.execute('DROP TABLE %s;' % qn)
        self.execute('DROP SEQUENCE %s;' % self.quote_name(get_sequence_name(table_name)))

    @generic.invalidate_table_constraints
    def alter_column(self, table_name, name, field, explicit_name=True):
        qn = self.quote_name(table_name)

        # hook for the field to do any resolution prior to it's attributes being queried
        if hasattr(field, 'south_init'):
            field.south_init()
        field = self._field_sanity(field)

        # Add _id or whatever if we need to
        field.set_attributes_from_name(name)
        if not explicit_name:
            name = field.column
        qn_col = self.quote_name(name)

        # First, change the type
        params = {
            'table_name':qn,
            'column': qn_col,
            'type': self._db_type_for_alter_column(field),
            'nullity': 'NOT NULL',
            'default': 'NULL'
        }
        if field.null:
            params['nullity'] = 'NULL'
        sqls = [self.alter_string_set_type % params]

        if not field.null and field.has_default():
            params['default'] = field.get_default()

        sqls.append(self.alter_string_set_default % params)

        #UNIQUE constraint
        unique_constraint = list(self._constraints_affecting_columns(qn, [qn_col]))

        if field.unique and not unique_constraint:
            self.create_unique(qn, [qn_col])
        elif not field.unique and unique_constraint:
            self.delete_unique(qn, [qn_col])

        #CHECK constraint is not handled

        for sql in sqls:
            try:
                self.execute(sql)
            except DatabaseError, exc:
                # Oracle complains if a column is already NULL/NOT NULL 
                if str(exc).find('ORA-01442') == -1 and str(exc).find('ORA-01451') == -1:
                    raise

    @generic.copy_column_constraints
    @generic.delete_column_constraints
    def rename_column(self, table_name, old, new):
        if old == new:
            # Short-circuit out
            return []
        self.execute('ALTER TABLE %s RENAME COLUMN %s TO %s;' % (
            self.quote_name(table_name),
            self.quote_name(old),
            self.quote_name(new),
        ))

    @generic.invalidate_table_constraints
    def add_column(self, table_name, name, field, keep_default=True):
        sql = self.column_sql(table_name, name, field)
        sql = self.adj_column_sql(sql)

        if sql:
            params = (
                self.quote_name(table_name),
                sql
            )
            sql = self.add_column_string % params
            self.execute(sql)

            # Now, drop the default if we need to
            if not keep_default and field.default is not None:
                field.default = NOT_PROVIDED
                self.alter_column(table_name, name, field, explicit_name=False)

    def delete_column(self, table_name, name):
        return super(DatabaseOperations, self).delete_column(self.quote_name(table_name), name)

    def _field_sanity(self, field):
        """
        This particular override stops us sending DEFAULTs for BooleanField.
        """
        if isinstance(field, models.BooleanField) and field.has_default():
            field.default = int(field.to_python(field.get_default()))
        return field



    def _fill_constraint_cache(self, db_name, table_name):
        qn = self.quote_name
        self._constraint_cache.setdefault(db_name, {}) 
        self._constraint_cache[db_name][table_name] = {} 

        rows = self.execute("""
            SELECT user_cons_columns.constraint_name,
                   user_cons_columns.column_name,
                   user_constraints.constraint_type
            FROM user_constraints
            JOIN user_cons_columns ON
                 user_constraints.table_name = user_cons_columns.table_name AND 
                 user_constraints.constraint_name = user_cons_columns.constraint_name
            WHERE user_constraints.table_name = '%s'
        """ % (qn(table_name)))

        for constraint, column, kind in rows:
            self._constraint_cache[db_name][table_name].setdefault(column, set())
            self._constraint_cache[db_name][table_name][column].add((kind, constraint))
        return
