"""
Main migration logic.
"""

import sys

from django.db import models
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from south import exceptions
from south.models import MigrationHistory
from south.db import db
from south.migration.base import all_migrations, Migrations
from south.migration.migrators import (Backwards, Forwards,
                                       DryRunMigrator, FakeMigrator)
from south.signals import pre_migrate, post_migrate


def check_dependencies(migrations, seen=[]):
    for migration in migrations:
        here = seen + [migration]
        if migration in seen:
            raise exceptions.CircularDependency(here)
        check_dependencies(migration.dependencies(), here)
    return True

def to_apply(forwards, done):
    return [m for m in forwards if m not in done]

def to_unapply(backwards, done):
    return [m for m in backwards if m in done]

def forwards_problems(pending, done, verbosity=0):
    problems = []
    for migration in pending:
        for m in migration.backwards_plan()[:-1]:
            if m in done:
                print " ! Migration %s should not have been applied before %s but was." % (m, migration)
                problems.append((migration, m))
    return problems

def backwards_problems(pending, done, verbosity=0):
    problems = []
    for migration in pending:
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

def check_migration_histories(histories):
    ghosts = find_ghost_migrations(histories)
    if ghosts:
        raise exceptions.GhostMigrations(ghosts)

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
    check_migration_histories(histories)
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
    missing_forwards = to_apply(forwards, current_migrations)
    # If they're all applied, we only know it's not backwards
    if not missing_forwards:
        direction = None
    # If the remaining migrations are strictly a right segment of the forwards
    # trace, we just need to go forwards to our target (and check for badness)
    else:
        problems = forwards_problems(missing_forwards, current_migrations, verbosity=verbosity)
        if problems:
            bad = True
        direction = 1
    
    # What about the whole backward trace then?
    if not bad:
        missing_backwards = to_apply(backwards, current_migrations)
        # If they're all missing, stick with the forwards decision
        if missing_backwards == backwards:
            pass
        # If what's missing is a strict left segment of backwards (i.e.
        # all the higher migrations) then we need to go backwards
        else:
            present_backwards = to_unapply(backwards, current_migrations)
            problems = backwards_problems(present_backwards, current_migrations, verbosity=verbosity)
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
            for migration in missing_forwards:
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
        for migration in present_backwards:
            migrator.migrate(migration)
    else:
        if verbosity:
            print "- Nothing to migrate."
    
    # Finally, fire off the post-migrate signal
    post_migrate.send(None, app=app_name)
