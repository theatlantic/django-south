# -*- coding: UTF-8 -*-

from django.db import models
from django.contrib.auth.models import User as UserAlias

from south.modelsinspector import add_introspection_rules

def default_func():
    return "yays"

# An empty case.
class Other1(models.Model): pass

# Nastiness.
class HorribleModel(models.Model):
    "A model to test the edge cases of model parsing"
    
    ZERO, ONE = range(2)
    
    # First, some nice fields
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    
    # A ForeignKey, to a model above, and then below
    o1 = models.ForeignKey(Other1)
    o2 = models.ForeignKey('Other2')
    
    # Now to something outside
    user = models.ForeignKey(UserAlias, related_name="horribles")
    
    # Unicode!
    code = models.CharField(max_length=25, default="↑↑↓↓←→←→BA")
    
    # Odd defaults!
    class_attr = models.IntegerField(default=ZERO)
    func = models.CharField(max_length=25, default=default_func)
    
    # Time to get nasty. Define a non-field choices, and use it
    choices = [('hello', '1'), ('world', '2')]
    choiced = models.CharField(max_length=20, choices=choices)
    
    class Meta:
        db_table = "my_fave"
        verbose_name = "Dr. Strangelove," + \
                     """or how I learned to stop worrying
and love the bomb"""
    
    # Now spread over multiple lines
    multiline = \
              models.TextField(
        )
    
# Special case.
class Other2(models.Model):
    # Try loading a field without a newline after it (inspect hates this)
    close_but_no_cigar = models.PositiveIntegerField(primary_key=True)

class CustomField(models.IntegerField):
    def __init__(self, an_other_model, **kwargs):
        super(CustomField, self).__init__(**kwargs)
        self.an_other_model = an_other_model

add_introspection_rules([
    (
        [CustomField],
        [],
        {'an_other_model': ('an_other_model', {})},
    ),
], ['^south\.tests\.fakeapp\.models\.CustomField'])

class BaseModel(models.Model):
    pass

class SubModel(BaseModel):
    others = models.ManyToManyField(Other1)
    custom = CustomField(Other2)

class CircularA(models.Model):
    c = models.ForeignKey('CircularC')

class CircularB(models.Model):
    a = models.ForeignKey(CircularA)

class CircularC(models.Model):
    b = models.ForeignKey(CircularB)

class Recursive(models.Model):
   self = models.ForeignKey('self')
