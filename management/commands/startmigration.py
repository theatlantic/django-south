from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import models
from optparse import make_option
from south import migration
import sys
import os
import re
import string
import random
import inspect
import parser

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--model', action='append', dest='model_list', type='string',
            help='Generate a Create Table migration for the specified model.  Add multiple models to this migration with subsequent --model parameters.'),
        make_option('--initial', action='store_true', dest='initial', default=False,
            help='Generate the initial schema for the app.'),
    )
    help = "Creates a new template migration for the given app"
    
    def handle(self, app=None, name="", model_list=[], initial=False, **options):
        # make sure --model and --all aren't both specified
        if initial and model_list:
            print "You cannot use --initial and other options together"
            return
            
        # specify the default name 'initial' if a name wasn't specified and we're
        # doing a migration for an entire app
        if not name and initial:
            name = 'initial'
            
        # if not name, there's an error
        if not name:
            print "You must name this migration"
            return
        
        if not app:
            print "Please provide an app in which to create the migration."
            return
            
        # See if the app exists
        app_models_module = models.get_app(app)
        if not app_models_module:
            print "App '%s' doesn't seem to exist, isn't in INSTALLED_APPS, or has no models." % app
            return
            
        # Determine what models should be included in this migration.
        models_to_migrate = []
        if initial:
            models_to_migrate = models.get_models(app_models_module)
            if not models_to_migrate:
                print "No models found in app '%s'" % (app)
                return
        else:
            for model_name in model_list:
                model = models.get_model(app, model_name)
                if not model:
                    print "Couldn't find model '%s' in app '%s'" % (model_name, app)
                    return
                    
                models_to_migrate.append(model)
                
        # Make the migrations directory if it's not there
        app_module_path = app_models_module.__name__.split('.')[0:-1]
        try:
            app_module = __import__('.'.join(app_module_path), {}, {}, [''])
        except ImportError:
            print "Couldn't find path to App '%s'." % app
            return
            
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
        forwards, backwards = '', ''
        if models_to_migrate:
            for model in models_to_migrate:
                table_name = model._meta.db_table
                fields = []
                for f in model._meta.local_fields:
                    # We use a list of tuples to get nice ordering
                    field_definition = generate_field_definition(model, f)
                    fields.append((f.name, field_definition))
                forwards += '''
        # Model '%s'
        db.create_table("%s", (
            %s
        ))''' % (
                    model._meta.object_name,
                    table_name,
                    ",\n            ".join(["('%s', %s)" % (f[0], f[1]) for f in fields]),
                )

                backwards += '''
        db.delete_table("%s")''' % table_name
                # Now go through local M2Ms and add extra stuff for them
        #         for m in model._meta.local_many_to_many:
        #             forwards += '''
        # # M2M field '%s'
        # db.create_table("%s", [
        #     {"name": "id", "type": "serial", "null": False, "unique": True},
        #     {"name": "%s", "type": "integer", "null": False, "related_to": ("%s", "%s")},
        #     {"name": "%s", "type": "integer", "null": False, "related_to": ("%s", "%s")},
        # ]) ''' % (
        #                 m.name,
        #                 m.m2m_db_table(),
        #                 m.m2m_column_name(),
        #                 table_name,
        #                 "id",
        #                 m.m2m_reverse_name(),
        #                 m.rel.to._meta.db_table,
        #                 "id",
        #         )
        #         
        #             backwards += '''
        # db.delete_table("%s")''' % m.m2m_db_table()
                
            forwards += '''
        
        db.send_create_signal('%s', ['%s'])''' % (
                app, 
                "','".join(model._meta.object_name for model in models_to_migrate)
                )
        
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
""" % ('.'.join(app_module_path), forwards, backwards))
        fp.close()
        print "Created %s." % new_filename


def generate_field_definition(model, field):
    """
    Inspects the source code of 'model' to find the code used to generate 'field'
    """
    def test_field(field_definition):
        try:
            parser.suite(field_definition)
            return True
        except SyntaxError:
            return False
    
    field_pieces = []
    found_field = False
    source = inspect.getsourcelines(model)
    if not source:
        raise Exception("Could not find source to model: '%s'" % (model.__name__))
        
    # look for a line starting with the field name
    start_field_re = re.compile(r'\s*%s\s*=\s*(.*)' % field.name)
    for line in source[0]:
        # if the field was found during a previous iteration, 
        # we're here because the field spans across multiple lines
        # append the current line and try again
        if found_field:
            field_pieces.append(line.strip())
            if test_field(' '.join(field_pieces)):
                return ' '.join(field_pieces)
            continue
        
        match = start_field_re.match(line)
        if match:
            found_field = True
            field_pieces.append(match.groups()[0])
            if test_field(' '.join(field_pieces)):
                return ' '.join(field_pieces)
    
    # TODO:
    # If field definition isn't found, try looking in models parents.
    # This should most likely work with just a recursive call to generate_field_definition
    # supplying the models parents and the current field
    
    # the 'id' field never gets defined, so return what django does by default
    # django.db.models.options::_prepare
    if field.name == 'id' and field.__class__ == models.AutoField:
        return "models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)"
            
    raise Exception("Couldn't find field definition for field: '%s' on model: '%s'" % (
        field.name, model))

