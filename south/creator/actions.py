"""
Actions - things like 'a model was removed' or 'a field was changed'.
Each one has a class, which can take the action description and insert code
blocks into the forwards() and backwards() methods, in the right place.
"""

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
    
    def triples_to_defs(self, fields):
        # Turn the (class, args, kwargs) format into a string
        for field, triple in fields.items():
            triple = remove_useless_attributes(triple, db=True)
            if triple is None:
                print "WARNING: Cannot get definition for '%s' on '%s'. Please edit the migration manually." % (
                    field,
                    model_key(model),
                )
                fields[field] = "<<??>>"
            else:
                fields[field] = "self.gf(%r)(%s)" % (
                    triple[0], # Field full path
                    ", ".join(triple[1] + ["%s=%s" % (kwd, val) for kwd, val in triple[2].items()]), # args and kwds
                )
        return fields
    
    
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

    def __init__(self, model):
        self.model = model

    def forwards_code(self):
        
        fields = modelsinspector.get_model_fields(self.model)
        field_defs = "\n            ".join(["(%r, %s)" % (name, defn) for name, defn in self.triples_to_defs(fields).items()])
        
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