from django.core.management.base import NoArgsCommand
from django.core.management.color import no_style
from optparse import make_option
from south import migration
from django.core.management.commands import syncdb
from django.conf import settings
import sys

class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option('--verbosity', action='store', dest='verbosity', default='1',
            type='choice', choices=['0', '1', '2'],
            help='Verbosity level; 0=minimal output, 1=normal output, 2=all output'),
        make_option('--noinput', action='store_false', dest='interactive', default=True,
            help='Tells Django to NOT prompt the user for input of any kind.'),
    )
    help = "Create the database tables for all apps in INSTALLED_APPS whose tables haven't already been created, except those which use migrations."

    def handle_noargs(self, **options):
        from django.db import models
        # Work out what uses migrations and so doesn't need syncing
        apps_needing_sync = []
        apps_migrated = []
        for app in models.get_apps():
            app_name = '.'.join( app.__name__.split('.')[0:-1] )
            migrations = migration.get_migrations(app)
            if migrations is None:
                apps_needing_sync.append(app_name)
            else:
                # This is a migrated app, leave it
                apps_migrated.append(app_name)
        # Run syncdb on only the ones needed
        old_installed, settings.INSTALLED_APPS = settings.INSTALLED_APPS, apps_needing_sync
        syncdb.Command().execute(**options)
        settings.INSTALLED_APPS = old_installed
        # Be obvious about what we did
        print "\nSynced:\n > %s" % "\n > ".join(apps_needing_sync)
        print "\nNot synced (use migrations):\n - %s" % "\n - ".join(apps_migrated)
        print "(use ./manage.py migrate to migrate these)"
