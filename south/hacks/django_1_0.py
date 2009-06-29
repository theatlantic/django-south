"""
Hacks for the Django 1.0/1.0.2 releases.
"""

from django.conf import settings
from django.db import models

class Hacks:
    
    def set_installed_apps(self, apps):
        """
        Sets Django's INSTALLED_APPS setting to be effectively the list passed in.
        """
        
        # Make sure it's a list.
        apps = list(apps)
        
        # This function will be monkeypatched into place.
        def new_get_apps():
            return apps
        
        # Monkeypatch in!
        models.get_apps_old, models.get_apps = models.get_apps, new_get_apps
        settings.INSTALLED_APPS, settings.OLD_INSTALLED_APPS = (
            apps,
            settings.INSTALLED_APPS,
        )
        self._redo_app_cache()
    
    
    def reset_installed_apps(self):
        """
        Undoes the effect of set_installed_apps.
        """
        models.get_apps = models.get_apps_old
        settings.INSTALLED_APPS = settings.OLD_INSTALLED_APPS
        self._redo_app_cache()
    
    
    def _redo_app_cache(self):
        """
        Used to repopulate AppCache after fiddling with INSTALLED_APPS.
        """
        from django.db.models.loading import AppCache
        a = AppCache()
        a.loaded = False
        a._populate()