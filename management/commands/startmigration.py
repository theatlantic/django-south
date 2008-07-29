from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import models
from optparse import make_option
from south import migration
import sys
import os
import string
import random

class Command(BaseCommand):
    option_list = BaseCommand.option_list
    help = "Creates a new template migration for the given app"

    def handle(self, app=None, name="", **options):
        if not app:
            print "Please provide an app in which to create the migration."
            return
        # See if the app exists
        try:
            app_module = __import__(app, {}, {}, ['migrations'])
        except ImportError:
            print "App '%s' doesn't seem to exist." % app
            return
        # Make the migrations directory if it's not there
        migrations_dir = os.path.join(
            os.path.dirname(app_module.__file__),
            "migrations",
        )
        if not os.path.isdir(migrations_dir):
            print "Creating migrations directory at '%s'..." % migrations_dir
            os.mkdir(migrations_dir)
            # Touch the init py file
            open(os.path.join(migrations_dir, "__init__.py"), "w").close()
        # See what filename is next in line. We assume they use numbers.
        migrations = migration.get_migration_files(app)
        highest_number = 0
        for migration_name in migrations:
            try:
                number = int(migration_name.split("_")[0])
                highest_number = max(highest_number, number)
            except ValueError:
                pass
        # Make the new filename
        new_filename = "%04i%s_%s.py" % (
            highest_number + 1,
            "".join([random.choice(string.letters.lower()) for i in range(0)]), # Possible random stuff insertion
            name,
        )
        fp = open(os.path.join(migrations_dir, new_filename), "w")
        fp.write("""
from south.db import db
from %s.models import *

class Migration:
    
    def forwards(self):
        # Write your forwards migration here
        pass
    
    def backwards(self):
        # Write your backwards migration here
        pass""" % app)
        fp.close()
