"""
South's fake ORM; lets you not have to write SQL inside migrations.
Roughly emulates the real Django ORM, to a point.
"""

import inspect

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
            try:
                app_name, model_name = name.split(".", 1)
            except ValueError:
                app_name = self.default_app
                model_name = name
                name = "%s.%s" % (app_name, model_name)
            
            self.models[name.lower()] = self.make_model(app_name, model_name, data)
        
        # And perform the second run to iron out any circular/backwards depends.
        self.retry_failed_fields()

    
    def __getattr__(self, key):
        fullname = (self.default_app+"."+key).lower()
        try:
            return self.models[fullname]
        except KeyError:
            raise AttributeError("The model '%s' from the app '%s' is not available in this migration." % (key, self.default_app))
    
    
    def __getitem__(self, key):
        key = key.lower()
        try:
            return self.models[key]
        except KeyError:
            try:
                app, model = key.split(".", 1)
            except ValueError:
                raise KeyError("The model '%s' is not in appname.modelname format." % key)
            else:
                raise KeyError("The model '%s' from the app '%s' is not available in this migration." % (model, app))
    
    
    def eval_in_context(self, code):
        "Evaluates the given code in the context of the migration file."
        
        # Drag in the migration module's locals (hopefully including models.py)
        fake_locals = dict(inspect.getmodule(self.cls).__dict__)
        
        # We add our models into the locals for the eval
        fake_locals.update(dict([
            (name.split(".")[-1], model)
            for name, model in self.models.items()
            if name.split(".")[0] == self.default_app
        ]))
        
        # And a fake _ function
        fake_locals['_'] = lambda x: x
        
        return eval(code, globals(), fake_locals)
    
    
    def make_meta(self, modelname, data):
        "Makes a Meta class out of a dict of eval-able arguments."
        results = {}
        for key, code in data.items():
            try:
                results[key] = self.eval_in_context(code)
            except (NameError, AttributeError), e:
                raise ValueError("Cannot successfully create meta field '%s' for model '%s': %s." % (
                    key, modelname, e
                ))
        return type("Meta", tuple(), results) 
    
    
    def make_model(self, app, name, data):
        "Makes a Model class out of the given app name, model name and pickled data."
        
        # Turn the Meta dict into a basic class
        meta = self.make_meta("%s.%s" % (app, name), data['Meta'])
        del data['Meta']
        
        failed_fields = {}
        fields = {}
        stub = False
        
        # Now, make some fields!
        for fname, params in data.items():
            if fname == "_stub":
                stub = bool(params)
                continue
            elif not params:
                raise ValueError("Field '%s' on model '%s.%s' has no definition." % (fname, app, name))
            elif isinstance(params, (str, unicode)):
                # It's a premade definition string! Let's hope it works...
                code = params
            elif len(params) == 1:
                code = "%s()" % params[0]
            elif len(params) == 3:
                code = "%s(%s)" % (
                    params[0],
                    ", ".join(
                        params[1] +
                        ["%s=%s" % (n, v) for n, v in params[2].items()]
                    ),
                )
            else:
                raise ValueError("Field '%s' on model '%s.%s' has a weird definition length (should be 1 or 3 items)." % (fname, app, name))
            
            try:
                field = self.eval_in_context(code)
            except (NameError, AttributeError):
                # It might rely on other models being around. Add it to the
                # model for the second pass.
                failed_fields[fname] = code
            else:
                fields[fname] = field
        
        # Find the app in the Django core, and get its module
        more_kwds = {}
        app_module = models.get_app(app)
        more_kwds['__module__'] = app_module.__name__
        
        more_kwds['Meta'] = meta
        
        # Make our model
        fields.update(more_kwds)
        model = type(
            name,
            (models.Model,),
            fields,
        )
        
        # If this is a stub model, change Objects to a whiny class
        if stub:
            model.objects = WhinyManager()
        
        if failed_fields:
            model._failed_fields = failed_fields
        
        return model
    
    def retry_failed_fields(self):
        "Tries to re-evaluate the _failed_fields for each model."
        for modelname, model in self.models.items():
            if hasattr(model, "_failed_fields"):
                for fname, code in model._failed_fields.items():
                    try:
                        field = self.eval_in_context(code)
                    except (NameError, AttributeError), e:
                        # It's failed again. Complain.
                        raise ValueError("Cannot successfully create field '%s' for model '%s': %s." % (
                            fname, modelname, e
                        ))
                    else:
                        # Startup that field.
                        model.add_to_class(fname, field)


class WhinyManager(object):
    "A fake manager that whines whenever you try to touch it. For stub models."
    
    def __getattr__(self, key):
        raise AttributeError("You cannot use items from a stub model.")