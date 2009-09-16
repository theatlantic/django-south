"""
GeoDjango introspection rules
"""

import django
from django.conf import settings

from south.modelsinspector import add_introspection_rules


def has_spatialite():
    "Checks for the presence of SpataiLite"
    try:
        from ctypes.util import find_library
    except ImportError:
        return False
    from django.conf import settings
    return bool(getattr(settings, 'SPATIALITE_LIBRARY_PATH', find_library('spatialite')))


def has_geos():
    try:
        from django.contrib.gis.geos import libgeos
    except (ImportError, OSError):
        return False
    else:
        return True


# First, work out if GIS is enabled
# (If it isn't importing the field will fail)
has_gis = has_geos() and \
          ((settings.DATABASE_ENGINE in ["postgresql", "postgresql_psycopg2", "mysql"]) or \
          (settings.DATABASE_ENGINE == "sqlite3" and has_spatialite()))

# Build a tuple of possible database errors
database_error_classes = tuple()
try:
    from psycopg2 import ProgrammingError
except ImportError:
    pass
else:
    database_error_classes += (ProgrammingError,)

if has_gis:
    # Alright,import the field
    try:
        from django.contrib.gis.db.models.fields import GeometryField
    except database_error_classes:
        has_gis = False
    else:
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