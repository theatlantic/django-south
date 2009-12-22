"""
Actions - things like 'a model was removed' or 'a field was changed'.
Each one has a class, which can take the action description and insert code
blocks into the forwards() and backwards() methods, in the right place.
"""

import sys
import datetime

from django.db.models.fields.related import RECURSIVE_RELATIONSHIP_CONSTANT
from django.db.models.fields import FieldDoesNotExist

from south import modelsinspector
from south.creator.freezer import remove_useless_attributes, model_key

class Action(object):
    """
    Generic base Action class. Contains utility methods for inserting into
    the forwards() and backwards() method lists.
    """
    
    def forwards_code(self):
        raise NotImplementedError
    
    def backwards_code(self):
        raise NotImplementedError
    
    def add_forwards(self, forwards):
        forwards.append(self.forwards_code())
    
    def add_backwards(self, backwards):
        backwards.append(self.backwards_code())
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        raise NotImplementedError
    
    @classmethod
    def triples_to_defs(cls, fields):
        # Turn the (class, args, kwargs) format into a string
        for field, triple in fields.items():
            fields[field] = cls.triple_to_def(triple)
        return fields
    
    @classmethod
    def triple_to_def(cls, triple):
        "Turns a single triple into a definition."
        triple = remove_useless_attributes(triple, db=True)
        if triple is None:
            print "WARNING: Cannot get definition for '%s' on '%s'. Please edit the migration manually." % (
                field,
                model_key(model),
            )
            return "<<??>>"
        else:
            return "self.gf(%r)(%s)" % (
                triple[0], # Field full path
                ", ".join(triple[1] + ["%s=%s" % (kwd, val) for kwd, val in triple[2].items()]), # args and kwds
            )
    
    
class AddModel(Action):
    """
    Addition of a model. Takes the Model subclass that is being created.
    """
    
    FORWARDS_TEMPLATE = '''
        # Adding model '%(model_name)s'
        db.create_table(%(table_name)r, (
            %(field_defs)s
        ))
        db.send_create_signal(%(app_label)r, [%(model_name)r])'''
    
    BACKWARDS_TEMPLATE = '''
        # Deleting model '%(model_name)s'
        db.delete_table(%(table_name)r)'''

    def __init__(self, model, model_def):
        self.model = model
        self.model_def = model_def
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " + Added model %s.%s" % (
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )

    def forwards_code(self):
        
        field_defs = "\n            ".join([
            "(%r, %s)" % (name, defn) for name, defn
            in self.triples_to_defs(self.model_def).items()
        ])
        
        return self.FORWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.db_table,
            "app_label": self.model._meta.app_label,
            "field_defs": field_defs,
        }

    def backwards_code(self):
        return self.BACKWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.db_table,
        }
    
    
class DeleteModel(AddModel):
    """
    Deletion of a model. Takes the Model subclass that is being created.
    """
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " - Deleted model %s.%s" % (
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )

    def forwards_code(self):
        return AddModel.backwards_code(self)

    def backwards_code(self):
        return AddModel.forwards_code(self)
    
    
class AddField(Action):
    """
    Adds a field to a model. Takes a Model class and the field name.
    """
    
    FORWARDS_TEMPLATE = '''
        # Adding field '%(model_name)s.%(field_name)s'
        db.add_field(%(table_name)r, %(field_name)r, %(field_def)s)'''
    
    BACKWARDS_TEMPLATE = '''
        # Deleting field '%(model_name)s.%(field_name)s'
        db.delete_field(%(table_name)r, %(field_name)r)'''
    
    def __init__(self, model, field, field_def):
        self.model = model
        self.field_name = field
        self.field_def = field_def
        
        # See if they've made a NOT NULL column but also have no default (far too common)
        is_null = self.field_def[2].get("null", False)
        default = self.field_def[2].get("default", None)
        if not is_null and not default:
            # Oh dear. Ask them what to do.
            print " ? The field '%s.%s' does not have a default specified, yet is NOT NULL." % (
                self.model._meta.object_name,
                self.field_name,
            )
            print " ? Since you are adding or removing this field, you MUST specify a default"
            print " ? value to use for existing rows. Would you like to:"
            print " ?  1. Quit now, and add a default to the field in models.py"
            print " ?  2. Specify a one-off value to use for existing columns now"
            while True: 
                choice = raw_input(" ? Please select a choice: ")
                if choice == "1":
                    sys.exit(1)
                elif choice == "2":
                    break
                else:
                    print " ! Invalid choice."
            # OK, they want to pick their own one-time default. Who are we to refuse?
            print " ? Please enter Python code for your one-off default value."
            print " ? The datetime module is available, so you can do e.g. datetime.date.today()"
            while True:
                code = raw_input(" >>> ")
                if not code:
                    print " ! Please enter some code, or 'exit' (with no quotes) to exit."
                elif code == "exit":
                    sys.exit(1)
                else:
                    try:
                        result = eval(code, {}, {"datetime": datetime})
                    except (SyntaxError, NameError), e:
                        print " ! Invalid input: %s" % e
                    else:
                        break
            # Right, add the default in.
            self.field_def[2]['default'] = repr(result)
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " + Added field %s on %s.%s" % (
            self.field_name,
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )
    
    def forwards_code(self):
        
        return self.FORWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.db_table,
            "field_name": self.field_name,
            "field_def": self.triple_to_def(self.field_def),
        }

    def backwards_code(self):
        return self.BACKWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.db_table,
            "field_name": self.field_name,
        }
    
    
class DeleteField(AddField):
    """
    Removes a field from a model. Takes a Model class and the field name.
    """
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " - Deleted field %s on %s.%s" % (
            self.field_name,
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )
    
    def forwards_code(self):
        return AddField.backwards_code(self)

    def backwards_code(self):
        return AddField.forwards_code(self)


class AddUnique(Action):
    """
    Adds a unique constraint to a model. Takes a Model class and the field names.
    """
    
    FORWARDS_TEMPLATE = '''
        # Adding unique constraint on '%(model_name)s', fields %(fields)s
        db.add_unique(%(table_name)r, %(fields)r)'''
    
    BACKWARDS_TEMPLATE = '''
        # Removing unique constraint on '%(model_name)s', fields %(fields)s
        db.delete_unique(%(table_name)r, %(fields)r)'''
    
    def __init__(self, model, fields):
        self.model = model
        self.fields = fields
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " + Added unique constraint for %s on %s.%s" % (
            self.fields,
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )
    
    def forwards_code(self):
        
        return self.FORWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.db_table,
            "fields": self.fields,
        }

    def backwards_code(self):
        return self.BACKWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.db_table,
            "fields": self.fields,
        }


class DeleteUnique(AddUnique):
    """
    Removes a unique constraint from a model. Takes a Model class and the field names.
    """
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " - Deleted unique constraint for %s on %s.%s" % (
            self.fields,
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )
    
    def forwards_code(self):
        return AddUnique.backwards_code(self)

    def backwards_code(self):
        return AddUnique.forwards_code(self)


class AddM2M(Action):
    """
    Adds a unique constraint to a model. Takes a Model class and the field names.
    """
    
    FORWARDS_TEMPLATE = '''
        # Adding M2M field %(field_name)s on '%(model_name)s'
        db.create_table('%(table_name)s', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('%(left_field)s', models.ForeignKey(orm[%(left_model_key)r], null=False)),
            ('%(right_field)s', models.ForeignKey(orm[%(right_model_key)r], null=False))
        ))'''
    
    BACKWARDS_TEMPLATE = '''
        # Removing M2M field %(field_name)s on '%(model_name)s'
        db.delete_table('%(table_name)s')'''
    
    def __init__(self, model, field):
        self.model = model
        self.field_name = field
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " + Added M2M %s on %s.%s" % (
            self.field_name,
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )
    
    def forwards_code(self):
        
        field = self.model._meta.get_field_by_name(self.field_name)[0]
        
        return self.FORWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "field_name": self.field_name,
            "table_name": field.m2m_db_table(),
            "left_field": field.m2m_column_name()[:-3], # Remove the _id part
            "left_model_key": model_key(self.model),
            "right_field": field.m2m_reverse_name()[:-3], # Remove the _id part
            "right_model_key": model_key(field.rel.to),
        }

    def backwards_code(self):
        
        field = self.model._meta.get_field_by_name(self.field_name)[0]
        
        return self.BACKWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "field_name": self.field_name,
            "table_name": field.m2m_db_table(),
        }


class DeleteM2M(AddM2M):
    """
    Adds a unique constraint to a model. Takes a Model class and the field names.
    """
    
    def console_line(self):
        "Returns the string to print on the console, e.g. ' + Added field foo'"
        return " - Deleted M2M %s on %s.%s" % (
            self.field_name,
            self.model._meta.app_label, 
            self.model._meta.object_name,
        )
    
    def forwards_code(self):
        return AddM2M.backwards_code(self)

    def backwards_code(self):
        return AddM2M.forwards_code(self)
    