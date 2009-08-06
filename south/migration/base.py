import datetime
import os
import re
import sys

from django.core.exceptions import ImproperlyConfigured
from django.db import models

from south import exceptions
from south.migration.utils import get_app_name
from south.orm import LazyFakeORM, FakeORM
from south.utils import memoize


def all_migrations(applications=None):
    """
    Returns all Migrations for all `applications` that are migrated.
    """
    if applications is None:
        applications = models.get_apps()
    for app in applications:
        try:
            yield Migrations(app)
        except exceptions.NoMigrations:
            pass

def Migrations(application):
    if isinstance(application, basestring):
        app_name = application
    else:
        app_name = application.__name__
    if app_name not in Migrations.cache:
        Migrations.cache[app_name] = _Migrations(application)
    return Migrations.cache[app_name]
Migrations.cache = {}

class _Migrations(list):
    """
    Holds a list of Migration objects for a particular app.
    """

    MIGRATION_FILENAME = re.compile(r'(?!__init__)' # Don't match __init__.py
                                    r'[^.]*'        # Don't match dotfiles
                                    r'\.py$')       # Match only .py files

    def __new__(cls, application):
        if isinstance(application, basestring):
            return cls.from_name(application)
        return super(_Migrations, cls).__new__(cls)

    def __init__(self, application):
        if hasattr(application, '__name__'):
            self._cache = {}
            self.application = application

    @classmethod
    def from_name(cls, app_name):
        app = models.get_app(app_name)
        module_name = get_app_name(app)
        try:
            module = sys.modules[module_name]
        except KeyError:
            __import__(module_name, {}, {}, [''])
            module = sys.modules[module_name]
        return cls(module)

    def get_application(self):
        return self._application

    def set_application(self, application):
        self._application = application
        if not hasattr(application, 'migrations'):
            try:
                module = __import__(application.__name__ + '.migrations', {}, {})
                application.migrations = module.migrations
                self._migrations = application.migrations
            except ImportError:
                raise exceptions.NoMigrations(application)
        self._load_migrations_module(application.migrations)

    application = property(get_application, set_application)

    def _load_migrations_module(self, module):
        self._migrations = module
        filenames = []
        dirname = os.path.dirname(self._migrations.__file__)
        for f in os.listdir(dirname):
            if self.MIGRATION_FILENAME.match(os.path.basename(f)):
                filenames.append(f)
        filenames.sort()
        self.extend(self.migration(f) for f in filenames)

    def migration(self, filename):
        name = Migration.strip_filename(filename)
        if name not in self._cache:
            self._cache[name] = Migration(self, name)
        return self._cache[name]

    def __getitem__(self, value):
        if isinstance(value, basestring):
            return self.migration(value)
        return super(_Migrations, self).__getitem__(value)

    def guess_migration(self, prefix):
        prefix = Migration.strip_filename(prefix)
        matches = [m for m in self if m.name().startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise exceptions.MultiplePrefixMatches(prefix, matches)
        else:
            raise exceptions.UnknownMigration(prefix, None)

    def app_name(self):
        return get_app_name(self._migrations)

    def full_name(self):
        return self._migrations.__name__

    def calculate_dependents(self):
        for migrations in all_migrations():
            for migration in migrations:
                migration.add_dependent(None)
                for dependency in migration.dependencies():
                    dependency.add_dependent(migration)


class Migration(object):
    def __init__(self, migrations, filename):
        """
        Returns the migration class implied by 'filename'.
        """
        self.migrations = migrations
        self.filename = filename

    def __str__(self):
        return self.app_name() + ':' + self.name()

    def __repr__(self):
        return u'<Migration: %s>' % unicode(self)

    def app_name(self):
        return self.migrations.app_name()

    @staticmethod
    def strip_filename(filename):
        return os.path.splitext(os.path.basename(filename))[0]

    def name(self):
        return self.strip_filename(os.path.basename(self.filename))

    def full_name(self):
        return self.migrations.full_name() + '.' + self.name()

    def migration(self):
        full_name = self.full_name()
        app_name = self.app_name()
        try:
            migration = sys.modules[full_name]
        except KeyError:
            try:
                migration = __import__(full_name, '', '', ['Migration'])
            except ImportError, e:
                raise exceptions.UnknownMigration(self, sys.exc_info())
            except Exception, e:
                raise exceptions.BrokenMigration(self, sys.exc_info())
        # Override some imports
        migration._ = lambda x: x  # Fake i18n
        migration.datetime = datetime
        return migration
    migration = memoize(migration)

    def migration_class(self):
        return self.migration().Migration

    def migration_instance(self):
        return self.migration_class()()
    migration_instance = memoize(migration_instance)

    def previous(self):
        index = self.migrations.index(self) - 1
        if index < 0:
            return None
        return self.migrations[index]
    previous = memoize(previous)

    def next(self):
        index = self.migrations.index(self) + 1
        if index >= len(self.migrations):
            return None
        return self.migrations[index]
    next = memoize(next)

    def dependencies(self):
        result = [self.previous()]
        if result[0] is None:
            result = []
        # Get forwards dependencies
        for app, name in getattr(self.migration_class(), 'depends_on', []):
            try:
                migrations = Migrations(app)
            except ImproperlyConfigured:
                raise exceptions.DependsOnUnmigratedApplication(self, app)
            migration = migrations.migration(name)
            try:
                migration.migration()
            except exceptions.UnknownMigration:
                raise exceptions.DependsOnUnknownMigration(self, migration)
            if migration.is_before(self) == False:
                raise exceptions.DependsOnHigherMigration(self, migration)
            result.append(migration)
        return result
    dependencies = memoize(dependencies)

    def add_dependent(self, migration):
        if not hasattr(self, '_dependents'):
            self._dependents = []
        if migration and migration not in self._dependents:
            self._dependents.insert(0, migration)

    def dependents(self):
        self.migrations.calculate_dependents()
        return self._dependents
    dependents = memoize(dependents)

    def forwards(self):
        return self.migration_instance().forwards

    def backwards(self):
        return self.migration_instance().backwards

    def forwards_plan(self):
        """
        Returns a list of Migration objects to be applied, in order.

        This list includes `self`, which will be applied last.
        """
        result = []
        # We need to apply all the migrations this one depends on
        for migration in self.dependencies():
            result.extend([m for m in migration.forwards_plan()
                           if m not in result])
        # Append ourselves to the result
        result.append(self)
        return result

    def backwards_plan(self):
        """
        Returns a list of Migration objects to be unapplied, in order.

        This list includes `self`, which will be unapplied last.
        """
        result = []
        # We need to apply all the migrations this one depends on
        for migration in self.dependents():
            result.extend([m for m in migration.backwards_plan()
                           if m not in result])
        # Append ourselves to the result
        result.append(self)
        return result

    def is_before(self, other):
        if self.migrations == other.migrations:
            if self.filename < other.filename:
                return True
            return False

    def is_after(self, other):
        if self.migrations == other.migrations:
            if self.filename > other.filename:
                return True
            return False

    def prev_orm(self):
        previous = self.previous()
        if previous is None:
            # First migration? The 'previous ORM' is empty.
            return FakeORM(None, self.app_name())
        return previous.orm()
    prev_orm = memoize(prev_orm)

    def orm(self):
        return LazyFakeORM(self.migration().Migration, self.app_name())
    orm = memoize(orm)

    def no_dry_run(self):
        migration_class = self.migration_class()
        try:
            return migration_class.no_dry_run
        except AttributeError:
            return False


def get_app_name(app):
    """
    Returns the _internal_ app name for the given app module.
    i.e. for <module django.contrib.auth.models> will return 'auth'
    """
    return app.__name__.split('.')[-2]
