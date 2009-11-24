"""
Actions - things like 'a model was removed' or 'a field was changed'.
Each one has a class, which can take the action description and insert code
blocks into the forwards() and backwards() methods, in the right place.
"""

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
        return self.FORWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.table_name,
            "app_label": self.model._meta.app_label,
            "field_defs": "???",
        }

    def backwards_code(self):
        return self.BACKWARDS_TEMPLATE % {
            "model_name": self.model._meta.object_name,
            "table_name": self.model._meta.table_name,
        }