"""
South's fake ORM; lets you not have to write SQL inside migrations.
Roughly emulates the real Django ORM, to a point.
"""

from django.db import models


class FakeORM(object):
    
    """
    Simulates the Django ORM at some point in time,
    using a frozen definition on the Migration class.
    """
    
    def __init__(self, cls, app):
        self.default_app = app
        self.cls = cls
        # Try loading the models off the migration class; default to no models.
        self.models = {}
        try:
            self.models_source = cls.models
        except AttributeError:
            return
        
        # Now, make each model's data into a FakeModel
        for name, data in self.models_source.items():
            # Make sure there's some kind of Meta
            if "Meta" not in data:
                data['Meta'] = {}
            # If we're given an app name, use that
            if "app" in data['Meta']:
                app_name = data['Meta']["app"]
                del data['Meta']["app"]
            # Else, assume it's the same app
            else:
                app_name = self.default_app
            self.models[name] = self.make_model(app_name, name, data)

    
    def __getattr__(self, key):
        if key in self.models:
            return self.models[key]
        else:
            raise AttributeError("The model '%s' is not available in this migration." % key)
    
    
    def make_model(self, app, name, data):
        "Makes a Model class out of the given app name, model name and pickled data."
        
        # Find the app in the Django core, and get its module
        app_module = models.get_app(app)
        data['__module__'] = app_module.__name__
        
        # Turn the Meta dict into a basic class
        data['Meta'] = type("Meta", tuple(), data['Meta'])
        
        model = type(
            name,
            (models.Model,),
            data,
        )
        
        return model

