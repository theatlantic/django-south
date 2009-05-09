"""
Like south.modelsparser, but using introspection where possible
rather than direct inspection of models.py.
"""

from django.db import models
from django.db.models.base import ModelBase


# Gives information about how to introspect certain fields.
# This is a list of triples; the first item is a list of fields it applies to,
# (note that isinstance is used, so superclasses are perfectly valuid here)
# the second is a list of positional argument descriptors, and the third
# is a list of keyword argument descriptors.
# Descriptors are of the form:
#  [attrname, options]
# Where attrname is the attribute on the field to get the value from, and options
# is an optional dict.
#
# The introspector uses the combination of all matching entries, in order.
introspection_details = [
    (
        (models.Field, ),
        [],
        {
            "null": ["null", {"default": False}],
            "blank": ["blank", {"default": False}],
        },
    ),
    (
        (models.ForeignKey, models.OneToOneField),
        [
            ["rel.to", {}],
        ],
        {},
    ),
]


# 2.4 compatability
any = lambda x: reduce(lambda y, z: y or z, x, False)


def matching_details(field):
    """
    Returns the union of all matching entries in introspection_details for the field.
    """
    our_args = []
    our_kwargs = {}
    for classes, args, kwargs in introspection_details:
        if any([isinstance(field, x) for x in classes]):
            our_args.extend(args)
            our_kwargs.update(kwargs)
    return our_args, our_kwargs


# Raised when fields have their default values.
class IsDefault(Exception): pass


def get_value(field, descriptor):
    attrname, options = descriptor
    value = field
    for part in attrname.split("."):
        value = getattr(value, part)
    if "default" in options and value == options['default']:
        raise IsDefault
    # Models get their own special repr()
    if type(value) is ModelBase:
        return "orm['%s.%s']" % (value._meta.app_label, value._meta.object_name)
    else:
        return repr(value)


def introspector(field):
    """
    Given a field, introspects its definition triple.
    """
    arg_defs, kwarg_defs = matching_details(field)
    args = []
    kwargs = {}
    # For each argument, use the descriptor to get the real value.
    for defn in arg_defs:
        try:
            args.append(get_value(field, defn))
        except IsDefault:
            pass
    for kwd, defn in kwarg_defs.items():
        try:
            kwargs[kwd] = get_value(field, defn)
        except IsDefault:
            pass
    return args, kwargs


def get_model_fields(model, m2m=False):
    """
    Given a model class, returns a dict of {field_name: field_triple} defs.
    """
    
    field_defs = {}
    inherited_fields = {}
    
    # Go through all bases (that are themselves models, but not Model)
    for base in model.__bases__:
        if base != models.Model and issubclass(base, models.Model):
            # Looks like we need their fields, Ma.
            inherited_fields.update(get_model_fields(base))
    
    # Now, go through all the fields and try to get their definition
    source = model._meta.local_fields[:]
    if m2m:
        source += model._meta.local_many_to_many
    
    for field in source:
        
        # Get the full field class path.
        field_class = field.__class__.__module__ + "." + field.__class__.__name__
        
        # Run this field through the introspector
        args, kwargs = introspector(field)
        
        field_defs[field.name] = (field_class, args, kwargs)
    
    return field_defs