"""
Main migration logic.
"""

import sys

from django.core.exceptions import ImproperlyConfigured

from south import exceptions
from south.models import MigrationHistory
from south.db import db
from south.migration.base import all_migrations, Migrations
from south.migration.migrators import (Backwards, Forwards,
                                       DryRunMigrator, FakeMigrator,
                                       LoadInitialDataMigrator)
from south.signals import pre_migrate, post_migrate


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

def currently_applied(histories):
    applied = []
    for history in histories:
        try:
            applied.append(history.get_migration())
        except ImproperlyConfigured:
            pass
    return applied

def get_dependencies(target, migrations):
    forwards = list
    backwards = list
    if target is None:
        backwards = migrations[0].backwards_plan
    else:
        forwards = target.forwards_plan
        # When migrating backwards we want to remove up to and
        # including the next migration up in this app (not the next
        # one, that includes other apps)
        migration_before_here = target.next()
        if migration_before_here:
            backwards = migration_before_here.backwards_plan
    return forwards, backwards

def get_direction(target, histories, migrations, verbosity):
    # Get the forwards and reverse dependencies for this target
    forwards, backwards = get_dependencies(target, migrations)
    # Get the list of currently applied migrations from the db
    applied = currently_applied(histories)
    # Is the whole forward branch applied?
    problems = None
    workplan = to_apply(forwards(), applied)
    if not workplan:
        # If they're all applied, we only know it's not backwards
        direction = None
    else:
        # If the remaining migrations are strictly a right segment of
        # the forwards trace, we just need to go forwards to our
        # target (and check for badness)
        problems = forwards_problems(workplan, applied, verbosity)
        direction = Forwards
    if not problems:
        # What about the whole backward trace then?
        backwards = backwards()
        missing_backwards = to_apply(backwards, applied)
        if missing_backwards != backwards:
            # If what's missing is a strict left segment of backwards (i.e.
            # all the higher migrations) then we need to go backwards
            workplan = to_unapply(backwards, applied)
            problems = backwards_problems(workplan, applied, verbosity)
            direction = Backwards
    return direction, problems, workplan

def get_migrator(direction, db_dry_run, fake, verbosity, load_initial_data):
    if not direction:
        return None
    migrator = direction(verbosity=verbosity)
    if db_dry_run:
        migrator = DryRunMigrator(migrator=migrator)
    elif fake:
        migrator = FakeMigrator(migrator=migrator)
    elif load_initial_data:
        migrator = LoadInitialDataMigrator(migrator=migrator)
    return migrator

def migrate_app(migrations, target_name=None, merge=False, fake=False, db_dry_run=False, yes=False, verbosity=0, load_initial_data=False, skip=False):
    app_name = migrations.app_name()
    verbosity = int(verbosity)
    db.debug = (verbosity > 1)
    # Fire off the pre-migrate signal
    pre_migrate.send(None, app=app_name)
    # If there aren't any, quit quizically
    if not migrations:
        print "? You have no migrations for the '%s' app. You might want some." % app_name
        return
    # Check there's no strange ones in the database
    histories = MigrationHistory.objects.filter(applied__isnull=False)
    check_migration_histories(histories)
    # Guess the target_name
    target = migrations.guess_migration(target_name)
    if verbosity:
        if target_name not in ('zero', None) and target.name() != target_name:
            print " - Soft matched migration %s to %s." % (target_name,
                                                           target.name())
        print "Running migrations for %s:" % app_name
    # Get the forwards and reverse dependencies for this target
    direction, problems, workplan = get_direction(target, histories,
                                                  migrations, verbosity)
    if problems and not (merge or skip):
        raise exceptions.InconsistentMigrationHistory()
    # Perform the migration
    migrator = get_migrator(direction,
                            db_dry_run, fake, verbosity, load_initial_data)
    if verbosity:
        if migrator:
            print migrator.title(target)
        else:
            print '- Nothing to migrate.'
    if migrator:
        success = migrator.migrate_many(target, workplan)
        # Finally, fire off the post-migrate signal
        if success:
            post_migrate.send(None, app=app_name)
