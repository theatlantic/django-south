import unittest
import datetime
import sys
import os
import StringIO

from south import migration
from south.migration import Migrations
from south.tests import Monkeypatcher
from south.utils import snd

# Add the tests directory so fakeapp is on sys.path
test_root = os.path.dirname(__file__)
sys.path.append(test_root)


class TestMigration(Monkeypatcher):
    def test_name(self):
        app = self.create_fake_app("fakeapp")
        self.assertEqual(
            ["0001_spam", "0002_eggs", "0003_alter_spam"],
            [m.name() for m in Migrations(app)]
        )
    
    
    def test_migclass(self):
        
        app = self.create_fake_app("fakeapp")
        
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration
        M3 = __import__("fakeapp.migrations.0003_alter_spam", {}, {}, ['Migration']).Migration
        
        self.assertEqual(
            [M1, M2, M3],
            [m.migration().Migration for m in Migrations(app)]
        )
    
    
class TestMigrations(Monkeypatcher):
    def test_all(self):
        
        M1 = Migrations(__import__("fakeapp", {}, {}, ['']))
        M2 = Migrations(__import__("otherfakeapp", {}, {}, ['']))
        
        self.assertEqual(
            [M1, M2],
            list(Migrations.all()),
        )
    
    
    def test_from_name(self):
        
        M1 = Migrations(__import__("fakeapp", {}, {}, ['']))
        
        self.assertEqual(M1, Migrations.from_name("fakeapp"))
        self.assertEqual(M1, Migrations(self.create_fake_app("fakeapp")))


    def test_migration(self):
        
        app = self.create_fake_app("fakeapp")
        
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration

        migration = Migrations(app)
        self.assertEqual(M1, migration.migration("0001_spam").migration().Migration)
        self.assertEqual(M2, migration.migration("0002_eggs").migration().Migration)
        
        # Temporarily redirect sys.stdout during this, it whinges.
        stdout, sys.stdout = sys.stdout, StringIO.StringIO()
        try:
            self.assertRaises((ImportError, ValueError), migration.migration("0001_jam").migration)
        finally:
            sys.stdout = stdout
    

class TestMigrationLogic(Monkeypatcher):

    """
    Tests if the various logic functions in migration actually work.
    """
    
    def test_all_migrations(self):
        
        migrations = migration.Migrations.from_name("fakeapp")
        othermigrations = migration.Migrations.from_name("otherfakeapp")
        
        self.assertEqual({
                migrations._migrations: {
                    "0001_spam": migrations.migration("0001_spam").migration().Migration,
                    "0002_eggs": migrations.migration("0002_eggs").migration().Migration,
                    "0003_alter_spam": migrations.migration("0003_alter_spam").migration().Migration,
                },
                othermigrations._migrations: {
                    "0001_first": othermigrations.migration("0001_first").migration().Migration,
                    "0002_second": othermigrations.migration("0002_second").migration().Migration,
                    "0003_third": othermigrations.migration("0003_third").migration().Migration,
                },
            },
            migration.all_migrations(),
        )
    
    
    def assertListEqual(self, list1, list2):
        list1 = list(list1)
        list2 = list(list2)
        list1.sort()
        list2.sort()
        return self.assertEqual(list1, list2)
    
    
    def test_apply_migrations(self):
        
        migrations = migration.Migrations.from_name("fakeapp")
        
        # We should start with no migrations
        self.assertEqual(list(migration.MigrationHistory.objects.all()), [])
        
        # Apply them normally
        migration.migrate_app(migrations, target_name=None, resolve_mode=None, fake=False, verbosity=0)
        
        # We should finish with all migrations
        self.assertListEqual(
            (
                (u"fakeapp", u"0001_spam"),
                (u"fakeapp", u"0002_eggs"),
                (u"fakeapp", u"0003_alter_spam"),
            ),
            migration.MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Now roll them backwards
        migration.migrate_app(migrations, target_name="zero", resolve_mode=None, fake=False, verbosity=0)
        
        # Finish with none
        self.assertEqual(list(migration.MigrationHistory.objects.all()), [])
    
    
    def test_migration_merge_forwards(self):
        
        migrations = migration.Migrations.from_name("fakeapp")
        
        # We should start with no migrations
        self.assertEqual(list(migration.MigrationHistory.objects.all()), [])
        
        # Insert one in the wrong order
        migration.MigrationHistory.objects.create(
            app_name = "fakeapp",
            migration = "0002_eggs",
            applied = datetime.datetime.now(),
        )
        
        # Did it go in?
        self.assertListEqual(
            (
                (u"fakeapp", u"0002_eggs"),
            ),
            migration.MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Apply them normally
        try:
            # Redirect the error it will print to nowhere
            stdout, sys.stdout = sys.stdout, StringIO.StringIO()
            migration.migrate_app(migrations, target_name=None, resolve_mode=None, fake=False, verbosity=0)
            sys.stdout = stdout
        except SystemExit:
            pass
        
        # Nothing should have changed (no merge mode!)
        self.assertListEqual(
            (
                (u"fakeapp", u"0002_eggs"),
            ),
            migration.MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Apply with merge
        migration.migrate_app(migrations, target_name=None, resolve_mode="merge", fake=False, verbosity=0)
        
        # We should finish with all migrations
        self.assertListEqual(
            (
                (u"fakeapp", u"0001_spam"),
                (u"fakeapp", u"0002_eggs"),
                (u"fakeapp", u"0003_alter_spam"),
            ),
            migration.MigrationHistory.objects.values_list("app_name", "migration"),
        )
        
        # Now roll them backwards
        migration.migrate_app(migrations, target_name="0002", resolve_mode=None, fake=False, verbosity=0)
        migration.migrate_app(migrations, target_name="0001", resolve_mode=None, fake=True, verbosity=0)
        migration.migrate_app(migrations, target_name="zero", resolve_mode=None, fake=False, verbosity=0)
        
        # Finish with none
        self.assertEqual(list(migration.MigrationHistory.objects.all()), [])
    
    def test_alter_column_null(self):
        def null_ok():
            from django.db import connection, transaction
            # the DBAPI introspection module fails on postgres NULLs.
            cursor = connection.cursor()
            try:
                cursor.execute("INSERT INTO southtest_spam (id, weight, expires, name) VALUES (100, 10.1, now(), NULL);")
            except:
                transaction.rollback()
                return False
            else:
                cursor.execute("DELETE FROM southtest_spam")
                transaction.commit()
                return True
        
        migrations = migration.Migrations.from_name("fakeapp")
        self.assertEqual(list(migration.MigrationHistory.objects.all()), [])
        
        # by default name is NOT NULL
        migration.migrate_app(migrations, target_name="0002", resolve_mode=None, fake=False, verbosity=0)
        self.failIf(null_ok())
        
        # after 0003, it should be NULL
        migration.migrate_app(migrations, target_name="0003", resolve_mode=None, fake=False, verbosity=0)
        self.assert_(null_ok())

        # make sure it is NOT NULL again
        migration.migrate_app(migrations, target_name="0002", resolve_mode=None, fake=False, verbosity=0)
        self.failIf(null_ok(), 'name not null after migration')
        
        # finish with no migrations, otherwise other tests fail...
        migration.migrate_app(migrations, target_name="zero", resolve_mode=None, fake=False, verbosity=0)
        self.assertEqual(list(migration.MigrationHistory.objects.all()), [])
    
    def test_dependencies(self):
        
        fakeapp = migration.Migrations.from_name("fakeapp")._migrations
        otherfakeapp = migration.Migrations.from_name("otherfakeapp")._migrations
        
        # Test a simple path
        tree = migration.dependency_tree()
        self.assertEqual(
            map(snd, migration.needed_before_forwards(tree, fakeapp, "0003_alter_spam")),
            ['0001_spam', '0002_eggs'],
        )
        
        # And a complex one, with both back and forwards deps
        self.assertEqual(
            map(snd, migration.needed_before_forwards(tree, otherfakeapp, "0003_third")),
            ['0001_spam', '0001_first', '0002_second', '0002_eggs', '0003_alter_spam'],
        )


class TestMigrationUtils(Monkeypatcher):
    def test_get_app_name(self):
        self.assertEqual(
            "southtest",
            migration.get_app_name(self.create_fake_app("southtest.models")),
        )
        self.assertEqual(
            "baz",
            migration.get_app_name(self.create_fake_app("foo.bar.baz.models")),
        )
    
    
    def test_get_app_fullname(self):
        self.assertEqual(
            "southtest",
            migration.get_app_fullname(self.create_fake_app("southtest.models")),
        )
        self.assertEqual(
            "foo.bar.baz",
            migration.get_app_fullname(self.create_fake_app("foo.bar.baz.models")),
        )
    
    
