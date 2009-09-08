"""
GeoDjango introspection rules
"""

import django
from django.conf import settings

from south.utils import has_spatialite
from south.modelsinspector import add_introspection_rules

# First, work out if GIS is enabled
# (If it isn't importing the field will fail)
has_gis = (settings.DATABASE_ENGINE in ["postgresql", "postgresql_psycopg2", "mysql"]) or \
          (settings.DATABASE_ENGINE == "sqlite3" and has_spatialite())
if has_gis:
    # Alright,import the field
    from django.contrib.gis.db.models.fields import GeometryField
    
    # Make some introspection rules
    if django.VERSION[0] == 1 and django.VERSION[1] >= 1:
        # Django 1.1's gis module renamed these.
        rules = [
            (
                (GeometryField, ),
                [],
                {
                    "srid": ["srid", {"default": 4326}],
                    "spatial_index": ["spatial_index", {"default": True}],
                    "dim": ["dim", {"default": 2}],
                },
            ),
        ]
    else:
        rules = [
            (
                (GeometryField, ),
                [],
                {
                    "srid": ["_srid", {"default": 4326}],
                    "spatial_index": ["_spatial_index", {"default": True}],
                    "dim": ["_dim", {"default": 2}],
                },
            ),
        ]
    
    # Install them
    add_introspection_rules(rules, ["^django\.contrib\.gis"])