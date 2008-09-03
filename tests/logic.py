import unittest
import sys
import os

from south import migration

# Add the tests directory so fakeapp is on sys.path
test_root = os.path.dirname(__file__)
sys.path.append(test_root)


class TestMigrationLogic(unittest.TestCase):

    """
    Tests if the various logic functions in migration actually work.
    """

    def create_fake_app(self, name):
        
        class Fake:
            pass
        
        fake = Fake()
        fake.__name__ = name
        return fake


    def create_test_app(self):
        
        class Fake:
            pass
        
        fake = Fake()
        fake.__name__ = "fakeapp.migrations"
        fake.__file__ = os.path.join(test_root, "fakeapp", "migrations", "__init__.py")
        return fake
    
    
    def monkeypatch(self):
        """Swaps out various Django calls for fake ones for our own nefarious purposes."""
        
        def new_get_apps():
            return ['fakeapp']
        
        from django.db import models
        from django.conf import settings
        models.get_apps_old, models.get_apps = models.get_apps, new_get_apps
        settings.INSTALLED_APPS, settings.OLD_INSTALLED_APPS = (
            ["fakeapp"],
            settings.INSTALLED_APPS,
        )
        self.redo_app_cache()
    setUp = monkeypatch
    
    
    def unmonkeypatch(self):
        """Undoes what monkeypatch did."""
        
        from django.db import models
        from django.conf import settings
        models.get_apps = models.get_apps_old
        settings.INSTALLED_APPS = settings.OLD_INSTALLED_APPS
        self.redo_app_cache()
    tearDown = unmonkeypatch
    
    
    def redo_app_cache(self):
        from django.db.models.loading import AppCache
        a = AppCache()
        a.loaded = False
        a._populate()
    

    def test_get_app_name(self):
        self.assertEqual(
            "southtest",
            migration.get_app_name(self.create_fake_app("southtest.migrations")),
        )
        self.assertEqual(
            "baz",
            migration.get_app_name(self.create_fake_app("foo.bar.baz.migrations")),
        )
    
    
    def test_get_migrated_apps(self):
        
        P1 = __import__("fakeapp.migrations", {}, {}, [''])
        
        self.assertEqual(
            [P1],
            list(migration.get_migrated_apps()),
        )
    
    
    def test_get_app(self):
        
        P1 = __import__("fakeapp.migrations", {}, {}, [''])
        
        self.assertEqual(P1, migration.get_app("fakeapp"))
        self.assertEqual(P1, migration.get_app(self.create_fake_app("fakeapp.models")))
    
    
    def test_get_app_fullname(self):
        self.assertEqual(
            "southtest",
            migration.get_app_fullname(self.create_fake_app("southtest.migrations")),
        )
        self.assertEqual(
            "foo.bar.baz",
            migration.get_app_fullname(self.create_fake_app("foo.bar.baz.migrations")),
        )
    
    
    def test_get_migration_names(self):
        
        app = self.create_test_app()
        
        self.assertEqual(
            ["0001_spam", "0002_eggs"],
            migration.get_migration_names(app),
        )
    
    
    def test_get_migration_classes(self):
        
        app = self.create_test_app()
        
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration
        
        self.assertEqual(
            [M1, M2],
            list(migration.get_migration_classes(app)),
        )
    
    
    def test_get_migration(self):
        
        app = self.create_test_app()
        
        # Can't use vanilla import, modules beginning with numbers aren't in grammar
        M1 = __import__("fakeapp.migrations.0001_spam", {}, {}, ['Migration']).Migration
        M2 = __import__("fakeapp.migrations.0002_eggs", {}, {}, ['Migration']).Migration
        
        self.assertEqual(M1, migration.get_migration(app, "0001_spam"))
        self.assertEqual(M2, migration.get_migration(app, "0002_eggs"))
        
        self.assertRaises(ValueError, migration.get_migration, app, "0001_jam")
    
    
    def test_all_migrations(self):
        
        app = migration.get_app("fakeapp")
        
        self.assertEqual(
            {app: {
                "0001_spam": migration.get_migration(app, "0001_spam"),
                "0002_eggs": migration.get_migration(app, "0002_eggs"),
            }},
            migration.all_migrations(),
        )