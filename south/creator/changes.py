"""
Contains things to detect changes - either using options passed in on the
commandline, or by using autodetection, etc.
"""

from django.db import models

class ManualChanges(object):
    """
    Detects changes by reading the command line.
    """
    
    def __init__(self, current_orm):
        self.current_orm = current_orm
    
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