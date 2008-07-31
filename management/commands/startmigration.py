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

    def handle(self, app=None, name="", model=None, **options):
        if not app:
            print "Please provide an app in which to create the migration."
            return
        # See if the app exists
        try:
            app_module = __import__(app, {}, {}, ['migrations','models'])
        except ImportError:
            print "App '%s' doesn't seem to exist." % app
            return
        # If there's a model, open it and have a poke
        if model:
            try:
                model = getattr(app_module.models, model)
            except AttributeError:
                print "The specified model '%s' doesn't seem to exist." % model
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
        # If there's a model, make the migration skeleton, else leave it bare
        if model:
            table_name = model._meta.db_table
            fields = []
            for f in model._meta.local_fields:
                # We use a list of tuples to get nice ordering
                type, type_param = genericify_type(f.db_type())
                field = [
                    ("name", f.column),
                    ("type", type),
                    ("type_param", type_param),
                    ("null", f.null),
                ]
                if f.primary_key:
                    field.append(('primary', True))
                if f.unique:
                    field.append(('unique', True))
                if f.rel:
                    field.append(('related_to', (
                        f.rel.to._meta.db_table,
                        f.rel.to._meta.get_field(f.rel.field_name).column,
                    )))
                fields.append(field)
            forwards = '''db.create_table("%s", [
            %s
        ])''' % (
                table_name,
                ",\n            ".join([
                    "{%s}" % ", ".join("%r: %r" % (x, y) for x, y in f)
                    for f in fields
                ]),
            )
            backwards = '''db.delete_table("%s")''' % table_name
        else:
            forwards = '"Write your forwards migration here"'
            backwards = '"Write your backwards migration here"'
        fp = open(os.path.join(migrations_dir, new_filename), "w")
        fp.write("""
from south.db import db
from %s.models import *

class Migration:
    
    def forwards(self):
        %s
    
    def backwards(self):
        %s
""" % (app, forwards, backwards))
        fp.close()
        print "Created %s." % new_filename


def genericify_type(typestr):
    if "(" not in typestr:
        type = typestr
        param = None
    else:
        type, param = typestr.split("(")
        param = param[:-1]
    # Make sure it doesn't need to be mapped back to a more generic type
    type = {
        "varchar": "string",
        "timestamp with time zone": "datetime",
    }.get(type, type)
    return type, param
