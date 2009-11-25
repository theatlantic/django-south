"""
Contains things to detect changes - either using options passed in on the
commandline, or by using autodetection, etc.
"""

from django.db import models

from south.creator.freezer import remove_useless_attributes

class AutoChanges(object):
    """
    Detects changes by 'diffing' two sets of frozen model definitions.
    """
    
    def __init__(self, migrations, old_defs, old_orm, new_defs):
        self.migrations = migrations
        self.old_defs = old_defs
        self.old_orm = old_orm
        self.new_defs = new_defs
    
    def current_model_from_key(self, key):
        app_label, model_name = key.split(".")
        return models.get_model(app_label, model_name)
    
    def get_changes(self):
        """
        Returns the difference between the old and new sets of models as a 5-tuple:
        added_models, deleted_models, added_fields, deleted_fields, changed_fields
        """
        
        deleted_models = set()
        added_fields = set()
        deleted_fields = set()
        changed_fields = []
        added_uniques = set()
        deleted_uniques = set()
        
        # See if anything's vanished
        for key in self.old_defs:
            if key not in self.new_defs:
                yield ("DeleteModel", {"model": self.old_orm[key]})
                deleted_models.add(key)
        
        # Or appeared
        for key in self.new_defs:
            if key not in self.old_defs:
                yield ("AddModel", {"model": self.current_model_from_key(key)})
        
        # Now, for every model that's stayed the same, check its fields.
        for key in self.old_defs:
            if key not in deleted_models:
                
                still_there = set()
                
                old_fields = set([x for x in self.old_defs[key].keys() if x != "Meta"])
                new_fields = set([x for x in self.new_defs[key].keys() if x != "Meta"])
                
                # Find fields that have vanished.
                for fieldname in old_fields:
                    if fieldname not in new_fields:
                        yield ("DeleteField", {"model": self.old_orm[key], "field": fieldname})
                
                # And ones that have appeared
                for fieldname in new_fields:
                    if fieldname not in old_fields:
                        yield ("AddField", {"model": self.current_model_from_key(key), "field": fieldname})
                
                # For the ones that exist in both models, see if they were changed
                for fieldname in old_fields.intersection(new_fields):
                    if self.different_attributes(
                     remove_useless_attributes(self.old_defs[key][fieldname], True),
                     remove_useless_attributes(self.new_defs[key][fieldname], True)):
                        yield ("ChangeField", {
                            "old_model": self.old_orm[key],
                            "new_model": self.current_model_from_key(key),
                            "field": fieldname,
                        })
                    # See if their uniques have changed
                    old_triple = self.old_defs[key][fieldname]
                    new_triple = self.new_defs[key][fieldname]
                    if self.is_triple(old_triple) and self.is_triple(new_triple):
                        if old_triple[2].get("unique", "False") != new_triple[2].get("unique", "False"):
                            # Make sure we look at the one explicitly given to see what happened
                            if "unique" in old_triple[2]:
                                if old_triple[2]['unique'] == "False":
                                    yield ("AddUnique", {
                                        "model": self.current_model_from_key(key),
                                        "fields": [fieldname],
                                    })
                                else:
                                    yield ("DeleteUnique", {
                                        "model": self.old_orm[key],
                                        "fields": [fieldname],
                                    })
                            else:
                                if new_triple[2]['unique'] == "False":
                                    yield ("DeleteUnique", {
                                        "model": self.old_orm[key],
                                        "fields": [fieldname],
                                    })
                                else:
                                    yield ("AddUnique", {
                                        "model": self.current_model_from_key(key),
                                        "fields": [fieldname],
                                    })

    @classmethod
    def is_triple(cls, triple):
        "Returns whether the argument is a triple."
        return isinstance(triple, (list, tuple)) and len(triple) == 3 and \
            isinstance(triple[0], (str, unicode)) and \
            isinstance(triple[1], (list, tuple)) and \
            isinstance(triple[2], dict)

    @classmethod
    def different_attributes(cls, old, new):
        """
        Backwards-compat comparison that ignores orm. on the RHS and not the left
        and which knows django.db.models.fields.CharField = models.CharField.
        Has a whole load of tests in tests/autodetection.py.
        """
        
        # If they're not triples, just do normal comparison
        if not cls.is_triple(old) or not cls.is_triple(new):
            return old != new
        
        # Expand them out into parts
        old_field, old_pos, old_kwd = old
        new_field, new_pos, new_kwd = new
        
        # Copy the positional and keyword arguments so we can compare them and pop off things
        old_pos, new_pos = old_pos[:], new_pos[:]
        old_kwd = dict(old_kwd.items())
        new_kwd = dict(new_kwd.items())
        
        # Remove comparison of the existence of 'unique', that's done elsewhere.
        # TODO: Make this work for custom fields where unique= means something else?
        if "unique" in old_kwd:
            del old_kwd['unique']
        if "unique" in new_kwd:
            del new_kwd['unique']
        
        # If the first bit is different, check it's not by dj.db.models...
        if old_field != new_field:
            if old_field.startswith("models.") and (new_field.startswith("django.db.models") \
             or new_field.startswith("django.contrib.gis")):
                if old_field.split(".")[-1] != new_field.split(".")[-1]:
                    return True
                else:
                    # Remove those fields from the final comparison
                    old_field = new_field = ""
        
        # If there's a positional argument in the first, and a 'to' in the second,
        # see if they're actually comparable.
        if (old_pos and "to" in new_kwd) and ("orm" in new_kwd['to'] and "orm" not in old_pos[0]):
            # Do special comparison to fix #153
            try:
                if old_pos[0] != new_kwd['to'].split("'")[1].split(".")[1]:
                    return True
            except IndexError:
                pass # Fall back to next comparison
            # Remove those attrs from the final comparison
            old_pos = old_pos[1:]
            del new_kwd['to']
        
        return old_field != new_field or old_pos != new_pos or old_kwd != new_kwd


class ManualChanges(object):
    """
    Detects changes by reading the command line.
    """
    
    def __init__(self):
        pass
    
    def get_changes(self):
        return [
            ("AddModel", {"model": self.current_orm['books.Book']}),
        ]
    
    
class InitialChanges(object):
    """
    Creates all models; handles --initial.
    """
    
    def __init__(self, migrations):
        self.migrations = migrations
    
    def get_changes(self):
        # Get the app's models
        for model in models.get_models(models.get_app(self.migrations.app_label())):
            yield ("AddModel", {"model": model})