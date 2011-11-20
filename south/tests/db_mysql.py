import unittest

from south.db import db, generic, mysql
from django.db import connection, models

class TestMySQLOperations(unittest.TestCase):
    """MySQL-specific tests"""
    def setUp(self):
        db.debug = False
        db.clear_deferred_sql()

    def tearDown(self):
        pass

    def _create_foreign_tables(self, main_name, reference_name):
        # Create foreign table and model
        Foreign = db.mock_model(model_name='Foreign', db_table=reference_name,
                                db_tablespace='', pk_field_name='id',
                                pk_field_type=models.AutoField,
                                pk_field_args=[])
        db.create_table(reference_name, [
                ('id', models.AutoField(primary_key=True)),
            ])
        # Create table with foreign key
        db.create_table(main_name, [
                ('id', models.AutoField(primary_key=True)),
                ('foreign', models.ForeignKey(Foreign)),
            ])
        return Foreign

    def test_constraint_references(self):
        """Tests that referred table is reported accurately"""
        main_table = 'test_cns_ref'
        reference_table = 'test_cr_foreign'
        db.start_transaction()
        self._create_foreign_tables(main_table, reference_table)
        db.execute_deferred_sql()
        db_name = db._get_setting('NAME')
        constraint = db._find_foreign_constraints(main_table, 'foreign_id')[0]
        constraint_name = 'foreign_id_refs_id_%x' % (abs(hash((main_table,
            reference_table))))
        print constraint + ': ' + constraint_name
        self.assertEquals(constraint_name, constraint)
        references = db.constraint_references(main_table, constraint)
        self.assertEquals((reference_table, 'id'), references)

