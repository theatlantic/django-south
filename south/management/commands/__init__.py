
# Common framework for syncdb actions

import copy

from django.core import management
from django.conf import settings

from south.management.commands.syncdb import Command as SyncCommand

class MigrateAndSyncCommand(SyncCommand):
    """Used for situations where "syncdb" is called by test frameworks."""
    
    option_list = copy.deepcopy(SyncCommand.option_list)
    
    for opt in option_list:
        if "--migrate" == opt.get_opt_string():
            opt.default = True
            break

def patch_for_test_db_setup():
    management.get_commands()
    if hasattr(settings, "SOUTH_TESTS_MIGRATE") and not settings.SOUTH_TESTS_MIGRATE:
        # point at the core syncdb command when creating tests
        # tests should always be up to date with the most recent model structure
        management._commands['syncdb'] = 'django.core'
    else:
        management._commands['syncdb'] = MigrateAndSyncCommand()