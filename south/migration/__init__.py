"""
Main migration logic.
"""

from copy import copy
import datetime
import inspect
import sys
import traceback

from django.db import models
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from south import exceptions
from south.models import MigrationHistory
from south.db import db
from south.migration.base import all_migrations, Migrations
from south.signals import pre_migrate, post_migrate, ran_migration


class Migrator(object):
    def __init__(self, verbosity=0):
        self.verbosity = int(verbosity)

    def print_status(self, migration):
        status = self.status(migration)
        if self.verbosity and status:
            print status

    def orm(self, migration):
        raise NotImplementedError()

    def backwards(self, migration):
        return self._wrap_direction(migration.backwards(), self.orm(migration))

    def direction(self, migration):
        raise NotImplementedError()

    def print_backwards(self, migration):
        old_debug, old_dry_run = db.debug, db.dry_run
        db.debug = db.dry_run = True
        try:
            self.backwards(migration)()
        except:
            db.debug, db.dry_run = old_debug, old_dry_run
            raise

    @staticmethod
    def _wrap_direction(direction, orm):
        args = inspect.getargspec(direction)
        if len(args[0]) == 1:
            # Old migration, no ORM should be passed in
            return direction
        return (lambda: direction(orm))

    def run_migration(self, migration):
        migration_function = self.direction(migration)
        db.start_transaction()
        try:
            migration_function()
            db.execute_deferred_sql()
        except:
            db.rollback_transaction()
            if not db.has_ddl_transactions:
                print ' ! Error found during real run of migration! Aborting.'
                print
                print ' ! Since you have a database that does not support running'
                print ' ! schema-altering statements in transactions, we have had to'
                print ' ! leave it in an interim state between migrations.'
                if self.torun == 'forwards':
                    print
                    print " ! You *might* be able to recover with:"
                    self.print_backwards(migration)
                print
                print ' ! The South developers regret this has happened, and would'
                print ' ! like to gently persuade you to consider a slightly'
                print ' ! easier-to-deal-with DBMS.'
            raise
        else:
            db.commit_transaction()

    def run(self, migration):
        # Get the correct ORM.
        db.current_orm = self.orm(migration)
        # If the database doesn't support running DDL inside a transaction
        # *cough*MySQL*cough* then do a dry run first.
        if not db.has_ddl_transactions:
            try:
                dry_run = DryRunMigrator(migrator=self, ignore_fail=False)
                dry_run.run_migration(migration)
            except:
                raise
                return False
        return self.run_migration(migration)

    def done_migrate(self, migration):
        db.start_transaction()
        try:
            # Record us as having done this
            self.record(migration)
        except:
            db.rollback_transaction()
            raise
        else:
            db.commit_transaction()

    def send_ran_migration(self, migration):
        ran_migration.send(None,
                           app=migration.app_name(),
                           migration=migration,
                           method=self.__class__.__name__.lower())

    def migrate(self, migration):
        """
        Runs the specified migration forwards/backwards, in order.
        """
        app = migration.migrations._migrations
        migration_name = migration.name()
        self.print_status(migration)
        result = self.run(migration)
        self.done_migrate(migration)
        self.send_ran_migration(migration)
        return result


class MigratorWrapper(object):
    def __init__(self, migrator, *args, **kwargs):
        self._migrator = copy(migrator)
        attributes = dict([(k, getattr(self, k))
                           for k in self.__class__.__dict__.iterkeys()
                           if not k.startswith('__')])
        self._migrator.__dict__.update(attributes)

    def __getattr__(self, name):
        return getattr(self._migrator, name)


class DryRunMigrator(MigratorWrapper):
    def __init__(self, ignore_fail=True, *args, **kwargs):
        super(DryRunMigrator, self).__init__(*args, **kwargs)
        self._ignore_fail = ignore_fail

    def _run_migration(self, migration):
        if migration.no_dry_run() and self.verbosity:
            print " - Migration '%s' is marked for no-dry-run."
            return
        db.dry_run = True
        db.debug, old_debug = False, db.debug
        pending_creates = db.get_pending_creates()
        db.start_transaction()
        migration_function = self.direction(migration)
        try:
            migration_function()
        except:
            raise exceptions.FailedDryRun(sys.exc_info())
        finally:
            db.rollback_transactions_dry_run()
            db.debug = old_debug
            db.clear_run_data(pending_creates)
            db.dry_run = False

    def run_migration(self, migration):
        try:
            self._run_migration(migration)
        except exceptions.FailedDryRun:
            if self._ignore_fail:
                return False
            raise

    def done_migrate(self, *args, **kwargs):
        pass

    def send_ran_migration(self, *args, **kwargs):
        pass


class FakeMigrator(MigratorWrapper):
    def __init__(self, *args, **kwargs):
        super(FakeMigrator, self).__init__(*args, **kwargs)

    def run(self, migration):
        if self.verbosity:
            print '   (faked)'

    def send_ran_migration(self, *args, **kwargs):
        pass


class Forwards(Migrator):
    """
    Runs the specified migration forwards, in order.
    """
    torun = 'forwards'

    def status(self, migration):
        return ' > %s' % migration

    def forwards(self, migration):
        return self._wrap_direction(migration.forwards(), self.orm(migration))

    direction = forwards

    def orm(self, migration):
        return migration.orm()

    @staticmethod
    def record(migration):
        # Record us as having done this
        record = MigrationHistory.for_migration(migration)
        record.applied = datetime.datetime.utcnow()
        record.save()


class Backwards(Migrator):
    """
    Runs the specified migration backwards, in order.
    """
    torun = 'backwards'

    def status(self, migration):
        return ' < %s' % migration

    def orm(self, migration):
        return migration.prev_orm()

    direction = Migrator.backwards

    @staticmethod
    def record(migration):
        # Record us as having not done this
        record = MigrationHistory.for_migration(migration)
        if record.id is not None:
            record.delete()


def check_dependencies(migrations, seen=[]):
    for migration in migrations:
        here = seen + [migration]
        if migration in seen:
            raise exceptions.CircularDependency(here)
        check_dependencies(migration.dependencies(), here)
    return True

def forwards_problems(forwards, done, verbosity=0):
    problems = []
    for migration in forwards:
        if migration not in done:
            for m in migration.backwards_plan()[:-1]:
                if m in done:
                    print " ! Migration %s should not have been applied before %s but was." % (m, migration)
                    problems.append((migration, m))
    return problems

def backwards_problems(backwards, done, verbosity=0):
    problems = []
    for migration in backwards:
        if migration in done:
            for m in migration.forwards_plan()[:-1]:
                if m not in done:
                    print " ! Migration %s should have been applied before %s but wasn't." % (m, migration)
                    problems.append((migration, m))
    return problems

def find_ghost_migrations(histories):
    result = []
    for history in histories:
        migration = history.get_migration()
        try:
            migration.migration()
        except exceptions.UnknownMigration:
            result.append(migration)
    return result

def migrate_app(migrations, target_name=None, resolve_mode=None, fake=False, db_dry_run=False, yes=False, verbosity=0, load_inital_data=False, skip=False):
    
    app_name = migrations.app_name()
    app = migrations._migrations
    verbosity = int(verbosity)
    db.debug = (verbosity > 1)
    
    # Fire off the pre-migrate signal
    pre_migrate.send(None, app=app_name)
    # If there aren't any, quit quizically
    if not migrations:
        print "? You have no migrations for the '%s' app. You might want some." % app_name
        return
    # Check that all the dependencies are sane
    check_dependencies(migrations)
    # Check there's no strange ones in the database
    histories = MigrationHistory.objects.filter(applied__isnull=False)
    ghost_migrations = find_ghost_migrations(histories)
    if ghost_migrations:
        print " ! These migrations are in the database but not on disk:"
        print "   - " + "\n   - ".join([str(m) for m in ghost_migrations])
        print " ! I'm not trusting myself; fix this yourself by fiddling"
        print " ! with the south_migrationhistory table."
        return
    # Say what we're doing
    if verbosity:
        print "Running migrations for %s:" % app_name
    # Guess the target_name
    if target_name not in ["zero", None]:
        target = migrations.guess_migration(target_name)
        if target.name() != target_name:
            if verbosity:
                print " - Soft matched migration %s to %s." % (target_name,
                                                               target.name())
            target_name = target.name()
    # Get the forwards and reverse dependencies for this target
    forwards = []
    backwards = []
    if target_name == None:
        target = migrations[-1]
        target_name = target.name()
    if target_name == "zero":
        backwards = migrations[0].backwards_plan()
    else:
        forwards = target.forwards_plan()
        # When migrating backwards we want to remove up to and including
        # the next migration up in this app (not the next one, that includes other apps)
        migration_before_here = target.next()
        if migration_before_here:
            backwards = migration_before_here.backwards_plan()
    
    # Get the list of currently applied migrations from the db
    current_migrations = []
    for history in histories:
        try:
            current_migrations.append(history.get_migration())
        except ImproperlyConfigured:
            pass
    
    direction = None
    bad = False
    
    # Work out the direction
    applied_for_this_app = histories.filter(app_name=app_name).order_by('-migration')[:1]
    if target_name == "zero":
        direction = -1
    elif not applied_for_this_app:
        direction = 1
    else:
        latest = applied_for_this_app[0].get_migration()
        if target.is_before(latest):
            direction = 1
        elif target.is_after(latest):
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
        problems = forwards_problems(forwards, current_migrations, verbosity=verbosity)
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
            problems = backwards_problems(backwards, current_migrations, verbosity=verbosity)
            if problems:
                bad = True
            direction = -1
    
    if bad and resolve_mode not in ['merge'] and not skip:
        print " ! Inconsistent migration history"
        print " ! The following options are available:"
        print "    --merge: will just attempt the migration ignoring any potential dependency conflicts."
        sys.exit(1)

    if direction == 1:
        migrator = Forwards(verbosity=verbosity)
        if db_dry_run:
            migrator = DryRunMigrator(migrator=migrator)
        elif fake:
            migrator = FakeMigrator(migrator=migrator)
        if verbosity:
            print " - Migrating forwards to %s." % target_name
        try:
            for migration in forwards:
                if migration not in current_migrations:
                    result = migrator.migrate(migration)
                    if result is False: # The migrations errored, but nicely.
                        return False
        finally:
            # Call any pending post_syncdb signals
            db.send_pending_create_signals()
        # Now load initial data, only if we're really doing things and ended up at current
        if not fake and not db_dry_run and load_inital_data and target == migrations[-1]:
            if verbosity:
                print " - Loading initial data for %s." % app_name
            # Override Django's get_apps call temporarily to only load from the
            # current app
            old_get_apps, models.get_apps = (
                models.get_apps,
                lambda: [models.get_app(app_name)],
            )
            # Load the initial fixture
            call_command('loaddata', 'initial_data', verbosity=verbosity)
            # Un-override
            models.get_apps = old_get_apps
    elif direction == -1:
        migrator = Backwards(verbosity=verbosity)
        if db_dry_run:
            migrator = DryRunMigrator(migrator=migrator)
        elif fake:
            migrator = FakeMigrator(migrator=migrator)
        if verbosity:
            print " - Migrating backwards to just after %s." % target_name
        for migration in backwards:
            if migration in current_migrations:
                migrator.migrate(migration)
    else:
        if verbosity:
            print "- Nothing to migrate."
    
    # Finally, fire off the post-migrate signal
    post_migrate.send(None, app=app_name)
