from collections import deque
import datetime
import os
import re
import sys

from django.core.exceptions import ImproperlyConfigured
from django.db import models

from south import exceptions
from south.migration.utils import depends, dfs, flatten, get_app_name
from south.orm import LazyFakeORM, FakeORM
from south.utils import memoize, ask_for_it_by_name
from south.migration.utils import app_label_to_app_module


def all_migrations(applications=None):
    """
    Returns all Migrations for all `applications` that are migrated.
    """
    if applications is None:
        applications = models.get_apps()
    for model_module in applications:
        # The app they've passed is the models module - go up one level
        app_name = ".".join(model_module.__name__.split(".")[:-1])
        app = ask_for_it_by_name(app_name)
        try:
            yield Migrations(app)
        except exceptions.NoMigrations:
            pass


class MigrationsMetaclass(type):
    
    """
    Metaclass which ensures there is only one instance of a Migrations for
    any given app.
    """
    
    def __init__(self, name, bases, dict):
        super(MigrationsMetaclass, self).__init__(name, bases, dict)
        self.instances = {}
    
    def __call__(self, application):
        # Work out the app label
        if isinstance(application, basestring):
            app_label = application.split('.')[-1]
        else:
            app_label = application.__name__.split('.')[-1]
        
        # If we don't already have an instance, make one
        if app_label not in self.instances:
            self.instances[app_label] = super(MigrationsMetaclass, self).__call__(app_label_to_app_module(app_label))
        
        return self.instances[app_label]


class Migrations(list):
    """
    Holds a list of Migration objects for a particular app.
    """
    
    __metaclass__ = MigrationsMetaclass
    
    MIGRATION_FILENAME = re.compile(r'(?!__init__)' # Don't match __init__.py
                                    r'[^.]*'        # Don't match dotfiles
                                    r'\.py$')       # Match only .py files

    def __init__(self, application):
        if hasattr(application, '__name__'):
            self._cache = {}
            self.application = application

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

    def _guess_migration(self, prefix):
        prefix = Migration.strip_filename(prefix)
        matches = [m for m in self if m.name().startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise exceptions.MultiplePrefixMatches(prefix, matches)
        else:
            raise exceptions.UnknownMigration(prefix, None)

    def guess_migration(self, target_name):
        if target_name == 'zero' or not self:
            return
        elif target_name is None:
            return self[-1]
        else:
            return self._guess_migration(prefix=target_name)

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
    
    """
    Class which represents a particular migration file on-disk.
    """
    
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
        "Tries to load the actual migration module"
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
        "Returns the Migration class from the module"
        return self.migration().Migration

    def migration_instance(self):
        "Instantiates the migration_class"
        return self.migration_class()()
    migration_instance = memoize(migration_instance)

    def previous(self):
        "Returns the migration that comes before this one in the sequence."
        index = self.migrations.index(self) - 1
        if index < 0:
            return None
        return self.migrations[index]
    previous = memoize(previous)

    def next(self):
        "Returns the migration that comes after this one in the sequence."
        index = self.migrations.index(self) + 1
        if index >= len(self.migrations):
            return None
        return self.migrations[index]
    next = memoize(next)

    def dependencies(self):
        "Returns the list of migrations this migration depends on."
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
            self._dependents = deque()
        if migration and migration not in self._dependents:
            self._dependents.appendleft(migration)

    def dependents(self):
        "Returns the list of migrations that depend on this one"
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
        return depends(self, self.__class__.dependencies)

    def _backwards_plan(self):
        return depends(self, self.__class__.dependents)

    def backwards_plan(self):
        """
        Returns a list of Migration objects to be unapplied, in order.

        This list includes `self`, which will be unapplied last.
        """
        return list(self._backwards_plan())

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
