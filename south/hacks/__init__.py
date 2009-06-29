"""
The hacks module encapsulates all the horrible things that play with Django
internals in one, evil place.
This top file will automagically expose the correct Hacks class.
"""

from south.hacks.django_1_0 import Hacks

hacks = Hacks()