"""
Contains things to detect changes - either using options passed in on the
commandline, or by using autodetection, etc.
"""

from django.db import models


class AutoChanges(object):
    """
    Detects changes by 'diffing' two sets of frozen model definitions.
    """
    
    def __init__(self, migrations, old_defs, old_orm, new_defs):
        self.migrations = migrations
        self.old_defs = old_defs
        self.old_orm = old_orm
        self.new_defs = new_defs
    
    def get_changes(self):
        """
        Returns the difference between the old and new sets of models as a 5-tuple:
        added_models, deleted_models, added_fields, deleted_fields, changed_fields
        """
        
        added_models = set()
        deleted_models = set()
        ignored_models = set() # Stubs for backwards
        continued_models = set() # Models that existed before and after
        added_fields = set()
        deleted_fields = set()
        changed_fields = []
        added_uniques = set()
        deleted_uniques = set()
        
        # See if anything's vanished
        for key in old:
            if key not in new:
                if "_stub" not in old[key]:
                    deleted_models.add(key)
                else:
                    ignored_models.add(key)
        
        # Or appeared
        for key in new:
            if key not in old:
                added_models.add(key)
        
        # Now, for every model that's stayed the same, check its fields.
        for key in old:
            if key not in deleted_models and key not in ignored_models:
                continued_models.add(key)
                still_there = set()
                # Find fields that have vanished.
                for fieldname in old[key]:
                    if fieldname != "Meta" and fieldname not in new[key]:
                        deleted_fields.add((key, fieldname))
                    else:
                        still_there.add(fieldname)
                # And ones that have appeared
                for fieldname in new[key]:
                    if fieldname != "Meta" and fieldname not in old[key]:
                        added_fields.add((key, fieldname))
                # For the ones that exist in both models, see if they were changed
                for fieldname in still_there:
                    if fieldname != "Meta":
                        if different_attributes(
                         remove_useless_attributes(old[key][fieldname], True),
                         remove_useless_attributes(new[key][fieldname], True)):
                            changed_fields.append((key, fieldname, old[key][fieldname], new[key][fieldname]))
                        # See if their uniques have changed
                        old_triple = old[key][fieldname]
                        new_triple = new[key][fieldname]
                        if is_triple(old_triple) and is_triple(new_triple):
                            if old_triple[2].get("unique", "False") != new_triple[2].get("unique", "False"):
                                # Make sure we look at the one explicitly given to see what happened
                                if "unique" in old_triple[2]:
                                    if old_triple[2]['unique'] == "False":
                                        added_uniques.add((key, (fieldname,)))
                                    else:
                                        deleted_uniques.add((key, (fieldname,)))
                                else:
                                    if new_triple[2]['unique'] == "False":
                                        deleted_uniques.add((key, (fieldname,)))
                                    else:
                                        added_uniques.add((key, (fieldname,)))

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