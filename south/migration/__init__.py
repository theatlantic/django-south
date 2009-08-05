"""
Main migration logic.
"""

import datetime
import os
import re
import sys
import traceback
import inspect

from django.conf import settings
from django.db import models
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from south import exceptions
from south.models import MigrationHistory
from south.db import db
from south.migration.utils import get_app_name, get_app_fullname
from south.orm import LazyFakeORM, FakeORM
from south.signals import *
from south.utils import memoize


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

    def name(self):
        return os.path.splitext(os.path.basename(self.filename))[0]

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
        # Setup our FakeORM
        migclass = migration.Migration
        migclass.orm = LazyFakeORM(migclass, app_name)
        return migration
    migration = memoize(migration)

    def previous(self):
        index = self.migrations.index(self) - 1
        if index < 0:
            return None
        return self.migrations[index]

    def next(self):
        index = self.migrations.index(self) + 1
        if index >= len(self.migrations):
            return None
        return self.migrations[index]

    def dependencies(self):
        result = [self.previous()]
        if result[0] is None:
            result = []
        migclass = self.migration().Migration
        # Get forwards dependencies
        for app, name in getattr(migclass, 'depends_on', []):
            try:
                migrations = Migrations.from_name(app)
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

    def forwards_plan(self):
        result = []
        # We need to apply all the migrations this one depends on
        for migration in self.dependencies():
            result.extend([m for m in migration.forwards_plan() if m not in result])
        # Append ourselves to the result
        result.append(self)
        return result

    def backwards_plan(self):
        result = []
        # We need to apply all the migrations this one depends on
        for migration in self.dependents():
            result.extend([m for m in migration.backwards_plan() if m not in result])
        # Append ourselves to the result
        result.append(self)
        return result

    def is_before(self, other):
        if self.migrations == other.migrations:
            if self.filename < other.filename:
                return True
            return False


MIGRATIONS_CACHE = {}


class Migrations(list):
    """
    Holds a list of Migration objects for a particular app.
    """

    MIGRATION_FILENAME = re.compile(r'(?!__init__)' # Don't match __init__.py
                                    r'[^.]*'        # Don't match dotfiles
                                    r'\.py$')       # Match only .py files

    def __new__(cls, application):
        app_name = application.__name__
        if app_name not in MIGRATIONS_CACHE:
            obj = list.__new__(cls)
            obj._initialized = False
            MIGRATIONS_CACHE[app_name] = obj
        return MIGRATIONS_CACHE[app_name]

    def __init__(self, application):
        if not self._initialized:
            self._cache = {}
            self.application = application
            self._initialized = True

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

    @classmethod
    def from_name(cls, app_name):
        try:
            return MIGRATIONS_CACHE[app_name]
        except KeyError:
            app = models.get_app(app_name)
            module_name = get_app_name(app)
            try:
                module = sys.modules[module_name]
            except KeyError:
                __import__(module_name, {}, {}, [''])
                module = sys.modules[module_name]
            return cls(module)

    @classmethod
    def all(cls):
        """
        Returns all migrations from all apps.
        """
        for mapp in models.get_apps():
            try:
                yield cls.from_name(mapp)
            except exceptions.NoMigrations:
                pass

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
        name, _ = os.path.splitext(os.path.basename(filename))
        if name not in self._cache:
            self._cache[name] = Migration(self, name)
        return self._cache[name]

    def app_name(self):
        return get_app_name(self._migrations)

    def full_name(self):
        return self._migrations.__name__

    def calculate_dependents(self):
        for migrations in self.all():
            for migration in migrations:
                migration.add_dependent(None)
                for dependency in migration.dependencies():
                    dependency.add_dependent(migration)


def get_migration(migrations, migration):
    application = sys.modules[get_app_name(migrations)]
    return Migrations(application).migration(migration).migration().Migration

def get_migration_names(migrations):
    application = sys.modules[get_app_name(migrations)]
    return [m.name() for m in Migrations(application)]

def all_migrations():
    return dict([
        (migrations._migrations,
         dict([(os.path.splitext(m.filename)[0], m.migration().Migration)
               for m in migrations]))
        for migrations in Migrations.all()
    ])

def trace(seen):
    return " -> ".join([unicode(s) for s in seen])

def check_dependencies(migrations, seen=[]):
    for migration in migrations:
        here = seen + [migration]
        if migration in seen:
            print "Found circular dependency: %s" % trace(here)
            sys.exit(1)
        check_dependencies(migration.dependencies(), here)

            
def dependency_tree():
    tree = {}
    for migrations in Migrations.all():
        check_dependencies(migrations)
        tree[migrations._migrations] = dict([(os.path.splitext(m.filename)[0],
                                              m.migration().Migration)
                                             for m in migrations])
    return tree


def needed_before_forwards(app_name, name, sameapp=True):
    """
    Returns a list of migrations that must be applied before (app, name),
    in the order they should be applied.
    Used to make sure a migration can be applied (and to help apply up to it).
    """
    return [(m.migrations._migrations, m.name()) for m in Migrations.from_name(app_name).migration(name).forwards_plan()][:-1]


def needed_before_backwards(app_name, name, sameapp=True):
    """
    Returns a list of migrations that must be unapplied before (app, name) is,
    in the order they should be unapplied.
    Used to make sure a migration can be unapplied (and to help unapply up to it).
    """
    return [(m.migrations._migrations, m.name()) for m in Migrations.from_name(app_name).migration(name).backwards_plan()][:-1]


def run_migrations(toprint, torun, recorder, app, migrations, fake=False, db_dry_run=False, verbosity=0):
    """
    Runs the specified migrations forwards/backwards, in order.
    """
    for migration in migrations:
        app_name = get_app_name(app)
        if verbosity:
            print toprint % (app_name, migration)
        
        # Get migration class
        klass = get_migration(app, migration)
        # Find its predecessor, and attach the ORM from that as prev_orm.
        all_names = get_migration_names(app)
        idx = all_names.index(migration)
        # First migration? The 'previous ORM' is empty.
        if idx == 0:
            klass.prev_orm = FakeORM(None, app)
        else:
            klass.prev_orm = get_migration(app, all_names[idx-1]).orm
        
        # If this is a 'fake' migration, do nothing.
        if fake:
            if verbosity:
                print "   (faked)"
        
        # OK, we should probably do something then.
        else:
            runfunc = getattr(klass(), torun)
            args = inspect.getargspec(runfunc)
            
            # Get the correct ORM.
            if torun == "forwards":
                orm = klass.orm
            else:
                orm = klass.prev_orm
            
            db.current_orm = orm
            
            # If the database doesn't support running DDL inside a transaction
            # *cough*MySQL*cough* then do a dry run first.
            if not db.has_ddl_transactions or db_dry_run:
                if not (hasattr(klass, "no_dry_run") and klass.no_dry_run):
                    db.dry_run = True
                    db.debug, old_debug = False, db.debug
                    pending_creates = db.get_pending_creates()
                    db.start_transaction()
                    try:
                        if len(args[0]) == 1:  # They don't want an ORM param
                            runfunc()
                        else:
                            runfunc(orm)
                            db.rollback_transactions_dry_run()
                    except:
                        traceback.print_exc()
                        print " ! Error found during dry run of migration! Aborting."
                        return False
                    db.debug = old_debug
                    db.clear_run_data(pending_creates)
                    db.dry_run = False
                elif db_dry_run:
                    print " - Migration '%s' is marked for no-dry-run."
                # If they really wanted to dry-run, then quit!
                if db_dry_run:
                    return
            
            db.start_transaction()
            try:
                if len(args[0]) == 1:  # They don't want an ORM param
                    runfunc()
                else:
                    runfunc(orm)
                db.execute_deferred_sql()
            except:
                db.rollback_transaction()
                if not db.has_ddl_transactions:
                    traceback.print_exc()
                    print " ! Error found during real run of migration! Aborting."
                    print
                    print " ! Since you have a database that does not support running"
                    print " ! schema-altering statements in transactions, we have had to"
                    print " ! leave it in an interim state between migrations."
                    if torun == "forwards":
                        print
                        print " ! You *might* be able to recover with:"
                        db.debug = db.dry_run = True
                        if len(args[0]) == 1:
                            klass().backwards()
                        else:
                            klass().backwards(klass.prev_orm)
                    print
                    print " ! The South developers regret this has happened, and would"
                    print " ! like to gently persuade you to consider a slightly"
                    print " ! easier-to-deal-with DBMS."
                raise
            else:
                db.commit_transaction()

        if not db_dry_run:
            db.start_transaction()
            try:
                # Record us as having done this
                recorder(app_name, migration)
            except:
                db.rollback_transaction()
                raise
            else:
                db.commit_transaction()
            if not fake:
                # Send a signal saying it ran
                ran_migration.send(None, app=app_name, migration=migration, method=torun)


def run_forwards(app, migrations, fake=False, db_dry_run=False, verbosity=0):
    """
    Runs the specified migrations forwards, in order.
    """
    
    def record(app_name, migration):
        # Record us as having done this
        record = MigrationHistory.for_migration(app_name, migration)
        record.applied = datetime.datetime.utcnow()
        record.save()
    
    return run_migrations(
        toprint = " > %s: %s",
        torun = "forwards",
        recorder = record,
        app = app,
        migrations = migrations,
        fake = fake,
        db_dry_run = db_dry_run,
        verbosity = verbosity,
    )


def run_backwards(app, migrations, ignore=[], fake=False, db_dry_run=False, verbosity=0):
    """
    Runs the specified migrations backwards, in order, skipping those
    migrations in 'ignore'.
    """
    
    def record(app_name, migration):
        # Record us as having not done this
        record = MigrationHistory.for_migration(app_name, migration)
        if record.id is not None:
            record.delete()
    
    return run_migrations(
        toprint = " < %s: %s",
        torun = "backwards",
        recorder = record,
        app = app,
        migrations = [x for x in migrations if x not in ignore],
        fake = fake,
        db_dry_run = db_dry_run,
        verbosity = verbosity,
    )


def forwards_problems(tree, forwards, done, verbosity=0):
    problems = []
    for app, name in forwards:
        if (app, name) not in done:
            for dapp, dname in needed_before_backwards(get_app_name(app), name):
                if (dapp, dname) in done:
                    print " ! Migration (%s, %s) should not have been applied before (%s, %s) but was." % (get_app_name(dapp), dname, get_app_name(app), name)
                    problems.append(((app, name), (dapp, dname)))
    return problems



def backwards_problems(tree, backwards, done, verbosity=0):
    problems = []
    for app, name in backwards:
        if (app, name) in done:
            for dapp, dname in needed_before_forwards(get_app_name(app), name):
                if (dapp, dname) not in done:
                    print " ! Migration (%s, %s) should have been applied before (%s, %s) but wasn't." % (get_app_name(dapp), dname, get_app_name(app), name)
                    problems.append(((app, name), (dapp, dname)))
    return problems


def migrate_app(migrations, target_name=None, resolve_mode=None, fake=False, db_dry_run=False, yes=False, verbosity=0, load_inital_data=False, skip=False):
    
    app_name = migrations.app_name()
    app = migrations._migrations
    verbosity = int(verbosity)
    db.debug = (verbosity > 1)
    
    # Fire off the pre-migrate signal
    pre_migrate.send(None, app=app_name)
    
    # Find out what delightful migrations we have
    check_dependencies(migrations)
    tree = dependency_tree()
    migrations = get_migration_names(app)
    
    # If there aren't any, quit quizically
    if not migrations:
        print "? You have no migrations for the '%s' app. You might want some." % app_name
        return
    
    if target_name not in migrations and target_name not in ["zero", None]:
        matches = [x for x in migrations if x.startswith(target_name)]
        if len(matches) == 1:
            target = migrations.index(matches[0]) + 1
            if verbosity:
                print " - Soft matched migration %s to %s." % (
                    target_name,
                    matches[0]
                )
            target_name = matches[0]
        elif len(matches) > 1:
            if verbosity:
                print " - Prefix %s matches more than one migration:" % target_name
                print "     " + "\n     ".join(matches)
            return
        else:
            print " ! '%s' is not a migration." % target_name
            return
    
    # Check there's no strange ones in the database
    ghost_migrations = []
    for m in MigrationHistory.objects.filter(applied__isnull = False):
        mod = Migrations.from_name(m.app_name)._migrations
        try:
            if mod not in tree or m.migration not in tree[mod]:
                ghost_migrations.append(m)
        except ImproperlyConfigured:
            pass
    
    if ghost_migrations:
        print " ! These migrations are in the database but not on disk:"
        print "   - " + "\n   - ".join(["%s: %s" % (x.app_name, x.migration) for x in ghost_migrations])
        print " ! I'm not trusting myself; fix this yourself by fiddling"
        print " ! with the south_migrationhistory table."
        return
    
    # Say what we're doing
    if verbosity:
        print "Running migrations for %s:" % app_name
    
    # Get the forwards and reverse dependencies for this target
    if target_name == None:
        target_name = migrations[-1]
    if target_name == "zero":
        forwards = []
        backwards = needed_before_backwards(app_name, migrations[0]) + [(app, migrations[0])]
    else:
        forwards = needed_before_forwards(app_name, target_name) + [(app, target_name)]
        # When migrating backwards we want to remove up to and including
        # the next migration up in this app (not the next one, that includes other apps)
        try:
            migration_before_here = migrations[migrations.index(target_name)+1]
            backwards = needed_before_backwards(app_name, migration_before_here) + [(app, migration_before_here)]
        except IndexError:
            backwards = []
    
    # Get the list of currently applied migrations from the db
    current_migrations = []
    for m in MigrationHistory.objects.filter(applied__isnull = False):
        try:
            current_migrations.append((Migrations.from_name(m.app_name)._migrations, m.migration))
        except ImproperlyConfigured:
            pass
    
    direction = None
    bad = False
    
    # Work out the direction
    applied_for_this_app = list(MigrationHistory.objects.filter(app_name=app_name, applied__isnull=False).order_by("migration"))
    if target_name == "zero":
        direction = -1
    elif not applied_for_this_app:
        direction = 1
    elif migrations.index(target_name) > migrations.index(applied_for_this_app[-1].migration):
        direction = 1
    elif migrations.index(target_name) < migrations.index(applied_for_this_app[-1].migration):
        direction = -1
    else:
        direction = None
    
    # Is the whole forward branch applied?
    missing = [step for step in forwards if step not in current_migrations]
    # If they're all applied, we only know it's not backwards
    if not missing:
        direction = None
    # If the remaining migrations are strictly a right segment of the forwards
    # trace, we just need to go forwards to our target (and check for badness)
    else:
        problems = forwards_problems(tree, forwards, current_migrations, verbosity=verbosity)
        if problems:
            bad = True
        direction = 1
    
    # What about the whole backward trace then?
    if not bad:
        missing = [step for step in backwards if step not in current_migrations]
        # If they're all missing, stick with the forwards decision
        if missing == backwards:
            pass
        # If what's missing is a strict left segment of backwards (i.e.
        # all the higher migrations) then we need to go backwards
        else:
            problems = backwards_problems(tree, backwards, current_migrations, verbosity=verbosity)
            if problems:
                bad = True
            direction = -1
    
    if bad and resolve_mode not in ['merge'] and not skip:
        print " ! Inconsistent migration history"
        print " ! The following options are available:"
        print "    --merge: will just attempt the migration ignoring any potential dependency conflicts."
        sys.exit(1)
    
    if direction == 1:
        if verbosity:
            print " - Migrating forwards to %s." % target_name
        try:
            for mapp, mname in forwards:
                if (mapp, mname) not in current_migrations:
                    result = run_forwards(mapp, [mname], fake=fake, db_dry_run=db_dry_run, verbosity=verbosity)
                    if result is False: # The migrations errored, but nicely.
                        return False
        finally:
            # Call any pending post_syncdb signals
            db.send_pending_create_signals()
        # Now load initial data, only if we're really doing things and ended up at current
        if not fake and not db_dry_run and load_inital_data and target_name == migrations[-1]:
            if verbosity:
                print " - Loading initial data for %s." % app_name
            # Override Django's get_apps call temporarily to only load from the
            # current app
            old_get_apps, models.get_apps = (
                models.get_apps,
                lambda: [models.get_app(get_app_name(app))],
            )
            # Load the initial fixture
            call_command('loaddata', 'initial_data', verbosity=verbosity)
            # Un-override
            models.get_apps = old_get_apps
    elif direction == -1:
        if verbosity:
            print " - Migrating backwards to just after %s." % target_name
        for mapp, mname in backwards:
            if (mapp, mname) in current_migrations:
                run_backwards(mapp, [mname], fake=fake, db_dry_run=db_dry_run, verbosity=verbosity)
    else:
        if verbosity:
            print "- Nothing to migrate."
    
    # Finally, fire off the post-migrate signal
    post_migrate.send(None, app=app_name)
