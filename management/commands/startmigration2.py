from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import models
from django.db.models.fields.related import RECURSIVE_RELATIONSHIP_CONSTANT
from django.contrib.contenttypes.generic import GenericRelation
from django.db.models.fields import FieldDoesNotExist
from optparse import make_option

from south import migration, modelsparser

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
        make_option('--add-field', action='append', dest='field_list', type='string',
            help='Generate an Add Column migration for the specified modelname.fieldname - you can use this multiple times to add more than one column.'),
        make_option('--initial', action='store_true', dest='initial', default=False,
            help='Generate the initial schema for the app.'),
    )
    help = "Creates a new template migration for the given app"
    
    def handle(self, app=None, name="", model_list=None, field_list=None, initial=False, **options):
        
        # If model_list is None, then it's an empty list
        model_list = model_list or []
        
        # If field_list is None, then it's an empty list
        field_list = field_list or []
        
        # make sure --model and --all aren't both specified
        if initial and (model_list or field_list):
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
        
        # See what fields need to be included
        fields_to_add = []
        for field_spec in field_list:
            model_name, field_name = field_spec.split(".", 1)
            model = models.get_model(app, model_name)
            if not model:
                print "Couldn't find model '%s' in app '%s'" % (model_name, app)
                return
            try:
                field = model._meta.get_field(field_name)
            except FieldDoesNotExist:
                print "Model '%s' doesn't have a field '%s'" % (model_name, field_name)
                return
            fields_to_add.append((model, field_name, field))
        
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
        
        # Make sure there's a migrations directory and __init__.py
        if not os.path.isdir(migrations_dir):
            print "Creating migrations directory at '%s'..." % migrations_dir
            os.mkdir(migrations_dir)
        init_path = os.path.join(migrations_dir, "__init__.py")
        if not os.path.isfile(init_path):
            # Touch the init py file
            print "Creating __init__.py in '%s'..." % migrations_dir
            open(init_path, "w").close()
        
        # See what filename is next in line. We assume they use numbers.
        migrations = migration.get_migration_names(migration.get_app(app))
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
        
        # Find the source file encoding, using PEP 0263's method
        encoding = None
        first_two_lines = inspect.getsourcelines(app_models_module)[0][:2]
        for line in first_two_lines:
            if re.search("coding[:=]\s*([-\w.]+)", line):
                encoding = line
        
        # Initialise forwards, backwards and models to blank things
        forwards = ""
        backwards = ""
        frozen_models = {} # Frozen models, used by the Fake ORM
        
        # Generate model migrations
        if models_to_migrate:
            for model in models_to_migrate:
                # Add the model to the frozen list
                frozen_models["%s.%s" % (app, model._meta.object_name)] = model
        
        # Default values for forwards/backwards
        if (not forwards) and (not backwards):
            forwards = '"Write your forwards migration here"'
            backwards = '"Write your backwards migration here"'
        
        # Fill out frozen model definitions
        for key, model in frozen_models.items():
            frozen_models[key] = remove_useless_attributes(
                modelsparser.get_model_fields(model)
            )
            meta = modelsparser.get_model_meta(model)
            if meta:
                frozen_models[key]['Meta'] = meta
        
        fp = open(os.path.join(migrations_dir, new_filename), "w")
        fp.write("""%s
from south.db import db
from django.db import models
from %s.models import *

class Migration:
    
    def forwards(self, orm):
        %s
    
    def backwards(self, orm):
        %s
    
    models = %s
""" % (encoding or "", '.'.join(app_module_path), forwards, backwards, pprint_frozen_models(frozen_models)))
        fp.close()
        print "Created %s." % new_filename


### Prettyprinters

def pprint_frozen_models(frozen_models):
    return "{\n        %s\n    }" % ",\n        ".join([
        "%r: %s" % (name, pprint_fields(fields))
        for name, fields in frozen_models.items()
    ])

def pprint_fields(fields):
    return "{\n            %s\n        }" % ",\n            ".join([
        "%r: %r" % (name, defn)
        for name, defn in sorted(fields.items())
    ])


### Output sanitisers

def remove_useless_attributes(fields):
    for name, field in fields.items():
        # If that has a 'choices' attribute, remove it.
        if "choices" in field[2]:
            del fields[name][2]['choices']
    return fields