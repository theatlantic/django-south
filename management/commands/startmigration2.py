"""
For backwards-compatability with the testing version in svn.
"""


from django.core.management.base import BaseCommand
from optparse import make_option

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--model', action='append', dest='added_model_list', type='string',
            help='Generate a Create Table migration for the specified model.  Add multiple models to this migration with subsequent --model parameters.'),
        make_option('--add-field', action='append', dest='added_field_list', type='string',
            help='Generate an Add Column migration for the specified modelname.fieldname - you can use this multiple times to add more than one column.'),
        make_option('--initial', action='store_true', dest='initial', default=False,
            help='Generate the initial schema for the app.'),
        make_option('--auto', action='store_true', dest='auto', default=False,
            help='Attempt to automatically detect differences from the last migration.'),
        make_option('--freeze', action='append', dest='freeze_list', type='string',
            help='Freeze the specified model(s). Pass in either an app name (to freeze the whole app) or a single model, as appname.modelname.'),
    )
    help = "Creates a new template migration for the given app"
    
    def handle(self, app=None, name="", added_model_list=None, added_field_list=None, initial=False, freeze_list=None, auto=False, **options):
        print "This command has now been renamed to 'startmigration'. Please use that."