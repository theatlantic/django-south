
import datetime
import os
import sys
from django.conf import settings
from models import MigrationHistory


def get_migrations(app):
    """
    Returns the list of migration modules for the given app, or None
    if it does not use migrations.
    """
    app_name = app.__name__
    app_name = '.'.join( app_name.split('.')[0:-1] )
    mod = __import__(app_name, {}, {}, ['migrations'])
    if hasattr(mod, 'migrations'):
        return getattr(mod, 'migrations')


def get_migration_files(app):
    """
    Returns a list of migration file names for the given app.
    """
    return sorted([
        filename[:-3]
        for filename in os.listdir(os.path.join(
            os.path.dirname(__import__(app,{},{},['migrations']).__file__),
            "migrations",
        ))
        if filename.endswith(".py") and filename != "__init__.py"
    ])


def get_migration(app_name, name):
    """
    Returns the migration class implied by 'name'.
    """
    module = __import__(app_name + ".migrations." + name, locals(), globals())
    return getattr(module.migrations, name).Migration


def run_forwards(app_name, migrations, fake=False):
    """
    Runs the specified migrations forwards, in order.
    """
    for migration in migrations:
        print " > %s" % migration
        klass = get_migration(app_name, migration)
        if fake:
            print "   (faked)"
        else:
            klass().forwards()
        # Record us as having done this
        record = MigrationHistory.for_migration(app_name, migration)
        record.applied = datetime.datetime.utcnow()
        record.save()


def run_backwards(app_name, migrations, ignore=[], fake=False):
    """
    Runs the specified migrations backwards, in order, skipping those
    migrations in 'ignore'.
    """
    for migration in migrations:
        if migration not in ignore:
            print " < %s" % migration
            klass = get_migration(app_name, migration)
            if fake:
                print "   (faked)"
            else:
                klass().backwards()
            # Record us as having not done this
            record = MigrationHistory.for_migration(app_name, migration)
            record.delete()


def migrate_app(migration_module, target_name=None, resolve_mode=None, fake=False):
    
    # Work out exactly what we're working on
    app_name = os.path.splitext(migration_module.__name__)[0]
    
    # Find out what delightful migrations we have
    migrations = sorted([
        filename[:-3]
        for filename in os.listdir(os.path.dirname(migration_module.__file__))
        if filename.endswith(".py") and filename != "__init__.py"
    ])
    
    # Find out what's already applied
    current_migrations = [m.migration for m in MigrationHistory.objects.filter(
        app_name = app_name,
        applied__isnull = False,
    )]
    current_migrations.sort()
    
    # Say what we're doing
    print "Running migrations for %s:" % app_name
    
    missing = []   # Migrations that should be there but aren't
    offset = 0     # To keep the lists in sync when missing ones crop up
    first = None   # The first missing migration (for rollback)
    current = len(migrations)  # The apparent latest migration.
    
    # Work out the missing migrations
    for i, migration in enumerate(migrations):
        if i >= len(current_migrations):
            current = i
            break
        elif current_migrations[i-offset] != migration:
            if not first:
                first = i
            missing.append(migration)
            offset += 1
    
    # Make sure the database doesn't have nonexistent migrations in it
    ghost_migrations = [m for m in current_migrations if m not in migrations]
    if ghost_migrations:
        print " ! These migrations are in the database but not on disk:"
        print "   - " + "\n   - ".join(ghost_migrations)
        print " ! I'm not trusting myself; fix this yourself by fiddling"
        print " ! with the south_migrationhistory table."
        return
    
    if offset:
        current += offset
    
    # Work out what they want us to go to.
    # Target (and current) are relative to migrations, not current_migrations
    if not target_name:
        target = len(migrations)
    else:
        if target_name == "zero":
            target = 0
        else:
            try:
                target = migrations.index(target_name) + 1
            except ValueError:
                print " ! '%s' is not a migration." % target_name
                return
    
    def describe_index(i):
        if i == 0:
            return "(no migrations applied)"
        else:
            return "(after %s)" % migrations[i-1]
    
    def one_before(what):
        index = migrations.index(what) - 1
        if index < 0:
            return "zero"
        else:
            return migrations[index]
    
    print " - Current migration: %s %s" % (current, describe_index(current))
    print " - Target migration: %s %s" % (target, describe_index(target))
    
    if missing:
        print " ! These migrations should have been applied already, but aren't:"
        print "   - " + "\n   - ".join(missing)
        if resolve_mode is None:
            print " ! Please re-run migrate with one of these switches:"
            print "   --skip: Ignore this migration mismatch and keep going"
            print "   --merge: Just apply the missing migrations out of order"
            print "   If you want to roll back to the first of these migrations"
            print "   and then roll forward, do:"
            print "     ./manage.py migrate --skip %s" % one_before(missing[0])
            print "     ./manage.py migrate"
            return
    
    # If we're using merge, and going forwards, merge
    if target >= current and resolve_mode == "merge" and missing:
        print " - Merging..."
        run_forwards(app_name, missing, fake=fake)
    
    # Now do the right direction.
    if target == current:
        print " - No migration needed."
    elif target < current:
        # Rollback
        print " - Rolling back..."
        run_backwards(app_name, reversed(current_migrations[target:current]), fake=fake)
    else:
        print " - Migrating..."
        run_forwards(app_name, migrations[current:target], fake=fake)