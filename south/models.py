from django.db import models

class MigrationHistory(models.Model):
    app_name = models.CharField(max_length=255)
    migration = models.CharField(max_length=255)
    applied = models.DateTimeField(blank=True)

    @classmethod
    def for_migration(cls, migration):
        try:
            return cls.objects.get(app_name=migration.app_label(),
                                   migration=migration.name())
        except cls.DoesNotExist:
            return cls(app_name=migration.app_label(),
                       migration=migration.name())

    def get_migrations(self):
        from south.migration.base import Migrations
        return Migrations(self.app_name)

    def get_migration(self):
        return self.get_migrations().migration(self.migration)
