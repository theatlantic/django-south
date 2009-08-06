"""
Main migration logic.
"""

import datetime
import sys
import traceback
import inspect

from django.db import models
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from south import exceptions
from south.models import MigrationHistory
from south.db import db
from south.migration.base import all_migrations, Migrations
from south.signals import pre_migrate, post_migrate, ran_migration


class Migrator(object):
    def __init__(self, fake=False, db_dry_run=False, verbosity=0):
        self.fake = fake
        self.db_dry_run = db_dry_run
        self.verbosity = int(verbosity)

    def print_status(self, migration):
        status = self.status(migration)
        if self.verbosity and status:
            print status

    def run(self, migration):
        # Get migration class
        klass = migration.migration().Migration
        # OK, we should probably do something then.
        runfunc = getattr(klass(), self.torun)
        args = inspect.getargspec(runfunc)
        # Get the correct ORM.
        if self.torun == 'forwards':
            orm = migration.orm()
        else:
            orm = migration.prev_orm()
        db.current_orm = orm
        # If the database doesn't support running DDL inside a transaction
        # *cough*MySQL*cough* then do a dry run first.
        if not db.has_ddl_transactions or self.db_dry_run:
            if not (hasattr(klass, 'no_dry_run') and klass.no_dry_run):
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
                    print ' ! Error found during dry run of migration! Aborting.'
                    return False
                db.debug = old_debug
                db.clear_run_data(pending_creates)
                db.dry_run = False
            elif db_dry_run:
                print " - Migration '%s' is marked for no-dry-run."
            # If they really wanted to dry-run, then quit!
            if self.db_dry_run:
                return
        # Run the migration
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
                print ' ! Error found during real run of migration! Aborting.'
                print
                print ' ! Since you have a database that does not support running'
                print ' ! schema-altering statements in transactions, we have had to'
                print ' ! leave it in an interim state between migrations.'
                if self.torun == 'forwards':
                    print
                    print " ! You *might* be able to recover with:"
                    db.debug = db.dry_run = True
                    if len(args[0]) == 1:
                        klass().backwards()
                    else:
                        klass().backwards(migration.prev_orm())
                print
                print ' ! The South developers regret this has happened, and would'
                print ' ! like to gently persuade you to consider a slightly'
                print ' ! easier-to-deal-with DBMS.'
            raise
        else:
            db.commit_transaction()

    def done_migrate(self, migration):
        if not self.db_dry_run:
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
        if not self.db_dry_run and not self.fake:
            ran_migration.send(None,
                               app=migration.app_name(),
                               migration=migration,
                               method=self.torun)

    def migrate(self, migration):
        """
        Runs the specified migration forwards/backwards, in order.
        """
        app = migration.migrations._migrations
        migration_name = migration.name()
        self.print_status(migration)
        if self.fake:
            # If this is a 'fake' migration, do nothing.
            if self.verbosity:
                print '   (faked)'
        else:
            self.run(migration)
        self.done_migrate(migration)


class Forwards(Migrator):
    """
    Runs the specified migration forwards, in order.
    """
    torun = 'forwards'

    def status(self, migration):
        return ' > %s' % migration

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
    # Guess the target_name
    if target_name not in ["zero", None]:
        target = migrations.guess_migration(target_name)
        if target.name() != target_name:
            if verbosity:
                print " - Soft matched migration %s to %s." % (target_name,
                                                               target.name())
            target_name = target.name()
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
    
    # Get the forwards and reverse dependencies for this target
    forwards = []
    backwards = []
    if target_name == None:
        target = migrations[-1]
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
        migrator = Forwards(fake=fake,
                            db_dry_run=db_dry_run,
                            verbosity=verbosity)
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
        migrator = Backwards(fake=fake,
                             db_dry_run=db_dry_run,
                             verbosity=verbosity)
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
