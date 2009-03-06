# -*- coding: utf8 -*-

from django.db import models
from django.contrib.auth.models import User

class Other1(models.Model): pass


class HorribleModel(models.Model):
    "A model to test the edge cases of model parsing"
    
    # First, some nice fields
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    
    # A ForeignKey, to a model above, and then below
    o1 = models.ForeignKey(Other1)
    o2 = models.ForeignKey('Other2')
    
    # Now to something outside
    user = models.ForeignKey(User, related_name="horribles")
    
    # Time to get nasty. Define a non-field choices, and use it
    choices = [('hello', '1'), ('world', '2')]
    choiced = models.CharField(max_length=20, choices=choices)
    
    # Now spread over multiple lines
    multiline = \
              models.TextField(
        )
    
    

class Other2(models.Model): pass
    