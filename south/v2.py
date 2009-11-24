"""
API versioning file; we can tell what kind of migrations things are
by what class they inherit from (if none, it's a v1).
"""


class BaseMigration(object):
    pass

class SchemaMigration(BaseMigration):
    pass

class DataMigration(BaseMigration):
    pass