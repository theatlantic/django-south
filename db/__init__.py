
# Establish the common DatabaseOperations instance, which we call 'db'.
# This code somewhat lifted from django evolution
from django.conf import settings
module_name = ['south.db', settings.DATABASE_ENGINE]
module = __import__('.'.join(module_name),{},{},[''])
db = module.DatabaseOperations()