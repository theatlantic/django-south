
.. _extending-introspection:

Extending Introspection
=======================

South's introspector, by default, only knows about core Django fields.
However, you can extend the introspector with rules for your own custom fields,
or those of third-party apps, if you wish.

Be aware that the rule-based introspector doesn't support every possible kind of
way constructor arguments are stored; if you require something very flexible,
look at using :ref:`south-field-triple` instead.

There are two different parts to the introspector, rules and field name
patterns. To extend the introspector's abilities, simply call
``south.modelsinspector.add_introspection_rules(rules=[], patterns=[])`` with a
list of rules, a list of patterns, or more commonly, both.

Rules
-----

Rules are what make up the crux of the introspector. They consist of a
class/classes to which the rules apply (the rules will be run for the class
and any field which subclasses it), and a set of 'rules' for positional and
keyword arguments. (In practice, South doesn't use the positional argument
functionality, and we encourage you not to).

A rule is a triple::

    (
        (models.ForeignKey, models.OneToOneField),
        [],
        {
            "to": ["rel.to", {}],
            "to_field": ["rel.field_name", {"default_attr": "rel.to._meta.pk.name"}],
            "related_name": ["rel.related_name", {"default": None}],
            "db_index": ["db_index", {"default": True}],
        },
    )

The first element is a tuple of either the names of, or actual, matching
classes (or superclasses), the second is the positional argument rules
(value rules in a list), and the third is the keyword argument rules
(a dictionary, with the keyword argument name as the key, and the
value rules as the value).

Value rules themselves are a list of two things; the first is the attribute
of the field to look at for the value of the rule (for example, "rel.to" or
"db_index" - you can include dots to traverse downwards), and the second is
a dict of parameters. If you don't have those, South will always put the value
of that attribute as the value for that keyword; the parameters are usually
there to allow an attribute to be omitted for clarity.

Parameters
^^^^^^^^^^

 - default: The default value of this field (directly as a Python object).
   If the value retrieved ends up being this, the keyword will be omitted
   from the frozen result. For example, the base Field class' "null" attribute
   has {'default':False}, so it's usually omitted, much like in the models.
 - default_attr: Similar to default, but the value given is another attribute
   to compare to for the default. This is used in to_field above, as this
   attribute's default value is the other model's pk name.
 - default_attr_concat: For when your default value is even more complex,
   default_attr_concat is a list where the first element is a format string,
   and the rest is a list of attribute names whose values should be formatted into the string.
 - ignore_if: Specifies an attribute that, if it coerces to true, causes this
   keyword to be omitted. Useful for ``db_index``, which has
   ``{'ignore_if': 'primary_key'}``, since it's always True in that case.
 
 
Field name patterns
-------------------

A list of regexes; if a field's full name (module plus class name) matches a
field name pattern, it is introspected, else it is parsed. This is needed
because of the subclass-following of the rules - for example, if you subclass
a Django field and change it, the introspector shouldn't try to introspect it.

Example (this is the default South list)::

    [
        "^django\.db",
        "^django\.contrib\.contenttypes\.generic",
        "^django\.contrib\.localflavor",
    ]

Examples
--------
    
For an example, see the GeoDjango rules module in South core,
or even the core rules in the inspector module.

Caveats
-------

If you have a custom field which adds other fields to the model dynamically
(i.e. it overrides contribute_to_class and adds more fields onto the model),
you'll need to write your introspection rules appropriately, to make South
ignore the extra fields at migration-freezing time, or to add a flag to your
field which tells it not to make the new fields again. An example can be
found `here <http://bitbucket.org/carljm/django-markitup/src/tip/markitup/fields.py#cl-68>`_.

.. _south-field-triple:

south_field_triple
==================

There are some cases where introspection of fields just isn't enough;
for example, field classes which dynamically change their database column
type based on options, or other odd things.

Note: :ref:`Extending the introspector <extending-introspection>` is often far
cleaner and easier than this method.

The method to implement for these fields is ``south_field_triple()``.

It should return the standard triple of::

 ('full.path.to.SomeFieldClass', ['positionalArg1', '"positionalArg2"'], {'kwarg':'"value"'})

(this is the same format used by the :ref:`ORM Freezer <orm-freezing>`;
South will just use your output verbatim).

Note that the strings are ones that will be passed into eval, so for this
reason, a variable reference would be ``'foo'`` while a string
would be ``'"foo"'``.

Example
-------

Here's an example of this method for django-modeltranslation's TranslationField.
This custom field stores the type it's wrapping in an attribute of itself,
so we'll just use that::

    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        # We'll just introspect the _actual_ field.
        from south.modelsinspector import introspector
        field_class = self.translated_field.__class__.__module__ + "." + self.translated_field.__class__.__name__
        args, kwargs = introspector(self.translated_field)
        # That's our definition!
        return (field_class, args, kwargs)
