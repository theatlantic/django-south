from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import models
from django.db.models.fields.related import RECURSIVE_RELATIONSHIP_CONSTANT
from django.contrib.contenttypes.generic import GenericRelation
from django.db.models.fields import FieldDoesNotExist
from optparse import make_option

try:
    set
except NameError:
    from sets import Set as set

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
        make_option('--freeze', action='append', dest='freeze_list', type='string',
            help='Freeze the specified model(s). Pass in either an app name (to freeze the whole app) or a single model, as appname.modelname.'),
    )
    help = "Creates a new template migration for the given app"
    
    def handle(self, app=None, name="", model_list=None, field_list=None, initial=False, freeze_list=None, **options):
        
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
        frozen_models = set() # Frozen models, used by the Fake ORM
        stub_models = set() # Frozen models, but only enough for relation ends (old mock models)
        
        # Add anything frozen (I almost called the dict Iceland...)
        if freeze_list:
            for item in freeze_list:
                if "." in item:
                    # It's a specific model
                    app_name, model_name = item.split(".", 1)
                    model = models.get_model(app_name, model_name)
                    if model is None:
                        print "Cannot find the model '%s' to freeze it." % item
                        return
                    frozen_models.add(model)
                else:
                    # Get everything in an app!
                    frozen_models.update(models.get_models(models.get_app(item)))
            # For every model in the freeze list, add in dependency stubs
            for model in frozen_models:
                stub_models.update(model_dependencies(model))
        
        # Add fields
        if fields_to_add:
            for model, field_name, field in fields_to_add:
                
                if isinstance(field, models.ManyToManyField):
                    # Add a stub model for each side
                    stub_models.add(model)
                    stub_models.add(field.rel.to)
                    # And a field defn, that's actually a table creation
                    forwards += CREATE_M2MFIELD_SNIPPET % (
                        model._meta.object_name,
                        field.name,
                        field.m2m_db_table(),
                        field.m2m_column_name()[:-3], # strip off the '_id' at the end
                        model._meta.object_name,
                        field.m2m_reverse_name()[:-3], # strip off the '_id' at the ned
                        field.rel.to._meta.object_name
                        )
                    backwards += DELETE_M2MFIELD_SNIPPET % (
                        model._meta.object_name,
                        field.name,
                        field.m2m_db_table()
                    )
                    continue
                
                # Add any dependencies
                stub_models.update(field_dependencies(field))
                
                # Work out the definition
                triple = modelsparser.get_model_fields(model)[field_name]
                field_definition = make_field_constructor(app, field, triple)
                
                forwards += CREATE_FIELD_SNIPPET % (
                    model._meta.object_name,
                    field.name,
                    model._meta.db_table,
                    field.name,
                    field_definition,
                )
                backwards += DELETE_FIELD_SNIPPET % (
                    model._meta.object_name,
                    field.name,
                    model._meta.db_table,
                    field.column,
                )
        
        # Generate model migrations
        if models_to_migrate:
            for model in models_to_migrate:
                # Add the model's dependencies to the stubs
                stub_models.update(model_dependencies(model))
                # Get the field definitions
                fields = modelsparser.get_model_fields(model)
                # Turn the (class, args, kwargs) format into a string
                for field, triple in fields.items():
                    triple = remove_useless_attributes(triple)
                    if triple is None:
                        print "WARNING: Cannot get definition for '%s' on '%s'. Please edit the migration manually." % (
                            field,
                            model_key(model),
                        )
                        fields[field] = FIELD_NEEDS_DEF_SNIPPET
                    else:
                        fields[field] = make_field_constructor(
                            app,
                            model._meta.get_field_by_name(field)[0],
                            triple,
                        )
                # Make the code
                forwards += CREATE_TABLE_SNIPPET % (
                    model._meta.object_name,
                    model._meta.db_table,
                    "\n            ".join(["('%s', %s)," % (fname, fdef) for fname, fdef in fields.items()]),
                )
                # And the backwards code
                backwards += DELETE_TABLE_SNIPPET % (
                    model._meta.object_name, 
                    model._meta.db_table
                )
        
        # Default values for forwards/backwards
        if (not forwards) and (not backwards):
            forwards = '"Write your forwards migration here"'
            backwards = '"Write your backwards migration here"'
        
        all_models = {}
        
        # Fill out frozen model definitions
        for model in frozen_models:
            fields = modelsparser.get_model_fields(model)
            # Remove useless attributes (like 'choices')
            for name, field in fields.items():
                fields[name] = remove_useless_attributes(field)
            # See if there's a Meta
            meta = modelsparser.get_model_meta(model)
            if meta:
                fields['Meta'] = remove_useless_meta(meta)
            # Add it to our models
            all_models[model_key(model)] = fields
        
        # Fill out stub model definitions
        for model in stub_models:
            if model in frozen_models:
                continue # We'd rather use full models than stubs.
            fields = modelsparser.get_model_fields(model)
            # Now, take only the PK (and a 'we're a stub' field) and freeze 'em
            pk = model._meta.pk.get_attname()
            fields = {
                pk: remove_useless_attributes(fields[pk]),
                "_stub": True,
            }
            # Meta is important too.
            meta = modelsparser.get_model_meta(model)
            if meta:
                fields['Meta'] = remove_useless_meta(meta)
            # Add it to the models
            all_models[model_key(model)] = fields
        
        # Do some model cleanup, and warnings
        for modelname, model in all_models.items():
            for fieldname, fielddef in model.items():
                # Remove empty-after-cleaning Metas.
                if fieldname == "Meta" and not fielddef:
                    del model['Meta']
                # Warn about undefined fields
                elif fielddef is None:
                    print "WARNING: Cannot get definition for '%s' on '%s'. Please edit the migration manually." % (
                        fieldname,
                        modelname,
                    )
                    model[fieldname] = FIELD_NEEDS_DEF_SNIPPET
        
        # Write the migration file
        fp = open(os.path.join(migrations_dir, new_filename), "w")
        fp.write(MIGRATION_SNIPPET % (
            encoding or "", '.'.join(app_module_path), 
            forwards, 
            backwards, 
            pprint_frozen_models(all_models)
        ))
        fp.close()
        print "Created %s." % new_filename


### Module handling functions

def model_key(model):
    "For a given model, return 'appname.modelname'."
    return ("%s.%s" % (model._meta.app_label, model._meta.object_name)).lower()


### Dependency resolvers

def model_dependencies(model):
    """
    Returns a set of models this one depends on to be defined; things like
    OneToOneFields as ID, ForeignKeys everywhere, etc.
    """
    depends = set()
    for field in model._meta.fields:
        depends.update(field_dependencies(field))
    return depends

def field_dependencies(field):
    depends = set()
    if isinstance(field, (models.OneToOneField, models.ForeignKey)):
        depends.add(field.rel.to)
    return depends
    


### Prettyprinters

def pprint_frozen_models(models):
    return "{\n        %s\n    }" % ",\n        ".join([
        "%r: %s" % (name, pprint_fields(fields))
        for name, fields in models.items()
    ])

def pprint_fields(fields):
    return "{\n            %s\n        }" % ",\n            ".join([
        "%r: %r" % (name, defn)
        for name, defn in sorted(fields.items())
    ])


### Output sanitisers


USELESS_KEYWORDS = ["choices", "help_text"]
def remove_useless_attributes(field):
    "Removes useless (for database) attributes from the field's defn."
    if field:
        for name in USELESS_KEYWORDS:
            if name in field[2]:
                del field[2][name]
    return field

USELESS_META = ["verbose_name", "verbose_name_plural"]
def remove_useless_meta(meta):
    "Removes useless (for database) attributes from the table's meta."
    if meta:
        for name in USELESS_META:
            if name in meta:
                del meta[name]
    return meta


### Turns (class, args, kwargs) triples into function defs.

def make_field_constructor(default_app, field, triple):
    """
    Given the defualt app, the field class,
    and the defn triple (or string), make the defition string.
    """
    # It might be a defn string already...
    if isinstance(triple, (str, unicode)):
        return triple
    # OK, do it the hard way
    if hasattr(field, "rel") and hasattr(field.rel, "to") and field.rel.to:
        rel_to = field.rel.to
    else:
        rel_to = None
    args = [poss_ormise(default_app, rel_to, arg) for arg in triple[1]]
    kwds = ["%s=%s" % (k, poss_ormise(default_app, rel_to, v)) for k,v in triple[2].items()]
    return "%s(%s)" % (triple[0], ", ".join(args+kwds))

def poss_ormise(default_app, rel_to, arg):
    """
    Given the name of something that needs orm. stuck on the front and
    a python eval-able string, possibly add orm. to it.
    """
    # If it's not a relative field, short-circuit out
    if not rel_to:
        return arg
    # Get the name of the other model
    rel_name = rel_to._meta.object_name
    # Is it in a different app? If so, use proper addressing.
    if rel_to._meta.app_label != default_app:
        real_name = "orm['%s.%s']" % (rel_to._meta.app_label, rel_name)
    else:
        real_name = "orm.%s" % rel_name
    # Now see if we can replace it.
    if arg == rel_name:
        return real_name
    return arg


### Various code snippets we need to use

MIGRATION_SNIPPET = """%s
from south.db import db
from django.db import models
from %s.models import *

class Migration:
    
    def forwards(self, orm):
        %s
    
    
    def backwards(self, orm):
        %s
    
    
    models = %s
"""
CREATE_TABLE_SNIPPET = '''
        # Model '%s'
        db.create_table(%r, (
            %s
        ))'''
DELETE_TABLE_SNIPPET = '''
        # Model '%s'
        db.delete_table(%r)'''
CREATE_FIELD_SNIPPET = '''
        # Adding field '%s.%s'
        db.add_column(%r, %r, %s)
        '''
DELETE_FIELD_SNIPPET = '''
        # Deleting field '%s.%s'
        db.delete_column(%r, %r)
        '''
CREATE_M2MFIELD_SNIPPET = '''
        # Adding ManyToManyField '%s.%s'
        db.create_table('%s', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('%s', models.ForeignKey(%s, null=False)),
            ('%s', models.ForeignKey(%s, null=False))
        )) '''
DELETE_M2MFIELD_SNIPPET = '''
        # Dropping ManyToManyField '%s.%s'
        db.drop_table('%s')'''
FIELD_NEEDS_DEF_SNIPPET = "<< PUT FIELD DEFINITION HERE >>"