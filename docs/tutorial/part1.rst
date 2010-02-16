
.. _tutorial-part-1:

Part 1: The Basics
==================

Welcome to South. This tutorial is designed to give you a runthrough of all the
major features; smaller projects may only use the first lot of features you
learn, but everything is built in for a reason!

South is often said to have a "steep learning curve". This is somewhat true,
but the hard part is in the middle - South is easy to plug in to a project,
but it's when you want to do moderately interesting things that you have to sit
down and learn how things work. There's plenty of documentation for you to read
through, but if you're stuck, you can always ask on our mailing list or IRC
channel.

If you've never heard of the idea of a migrations library, then please read
:ref:`what-are-migrations` first; that will help you get a better understanding
of what both South and others such as django-evolution are trying to achieve.

This tutorial assumes you have South installed correctly; if not, see the
`download page on our website <http://south.aeracode.org/wiki/Download>`_ for
instructions.


Apps and Migrations
-------------------

The first principle to learn is that, in South, individual apps are either
'migrated' or not - for example, the django.contrib.admin app isn't migrated, as
it has no migrations, whereas the app you'll create along with this tutorial
will have migrations, and so is 'migrated'.

The reason this is important is that, with South enabled, you will have two
ways of changing the database schema:

 - ``./manage.py syncdb`` - As before, this only creates models' tables directly,
   but with South enabled it will only do this for non-migrated apps.
 - ``./manage.py migrate`` - This command will change the database schema for
   migrated apps only.

South differentiates between migrated and non-migrated apps by seeing if they
have a appname/migrations/ directory. To create this directory, and create
migrations, there are a few important commands

 - ``./manage.py schemamigration`` - Creates schema migrations for apps, either blank
   ones, ones with user-specified actions, or ones with automatically-detected
   changes - we will cover all three of these uses.
 - ``./manage.py datamigration`` - Creates data migrations for apps. We'll cover
   these in a later part.
  

Kicking Off
-----------

First, create an application the usual way::

  django-admin.py startproject southtut
  cd southtut
  << add south to INSTALLED_APPS >>
  ./manage.py syncdb

Second, you will need an app, with a few models. It doesn't matter what;
if you want to follow the examples, make a new app called 'southdemo'::

  django-admin.py startapp southdemo
  
Give it the following models.py file::

  from django.db import models
  
  class Lizard(models.Model):
      
      age = models.IntegerField()
      name = models.CharField(max_length=30)
  
  class Adopter(models.Model):
      
      lizard = models.ForeignKey(Lizard)
      name = models.CharField(max_length=50)

Don't forget to update settings.py too:

 - Pick a ``DATABASE_ENGINE``, and set the relevant settings;
 - Add both 'south' and 'southdemo' to the list of ``INSTALLED_APPS``.
 
Now, we need to make our first migration. The way South works is that, on a
new installation, it will run through the entire history of migrations for each
app, rather than just using syncdb. This helps keep things consistent, and lets
you write migrations that put in complex initial data, but it does mean that
doing all migrations for an app, one after the other, should take a database
from blank to the most recent schema.

Specifically, this means that ``./manage.py migrate`` replaces ``./manage.py syncdb``
for applications with migrations; the effect of syncdb is recreated by the
migrations. You should not run syncdb on an application before you migrate it,
if it is a new app (if you are converting an existing app, see 
:ref:`converting-an-app`).

For this reason, the first migration has to be one that creates all the models
you currently have. startmigration accepts an ``--add-model`` parameter, which tells it
to make a migration that creates the named model, so we could do this::

 ./manage.py schemamigration southdemo initial --add-model Lizard --add-model Adopter

*(The arguments to startmigration are, in order, app name, migration name,
and then parameters)*

However, there is a shortcut for adding all models currently in the models.py
file, which is --initial::

 ./manage.py schemamigration southdemo --initial
 
*(You can also pass in a migration name here, but it will default to 'initial')*

Running this, we get::

  $ ./manage.py startmigration southdemo --initial
  Creating migrations directory at '/home/andrew/Programs/mornsq/southdemo/migrations'...
  Creating __init__.py in '/home/andrew/Programs/mornsq/southdemo/migrations'...
   + Added model 'southdemo.Lizard'
   + Added model 'southdemo.Adopter'
  Created 0001_initial.py.

As you can see, it has made our southdemo/migrations directory for us, as well
as putting an __init__.py file in it (to mark it as a Python package
- this is also required).

If you open up the migration file it made - 
`southdemo/migrations/0001_initial.py` - you'll see something like this::

  from south.db import db
  from django.db import models
  from southdemo.models import *
  
  class Migration:
      
      def forwards(self, orm):
          
          # Adding model 'Lizard'
          db.create_table('southdemo_lizard', (
              ('age', models.IntegerField()),
              ('id', models.AutoField(primary_key=True)),
              ('name', models.CharField(max_length=30)),
          ))
          db.send_create_signal('southdemo', ['Lizard'])
          
          # Adding model 'Adopter'
          db.create_table('southdemo_adopter', (
              ('lizard', models.ForeignKey(orm.Lizard)),
              ('id', models.AutoField(primary_key=True)),
              ('name', models.CharField(max_length=50)),
          ))
          db.send_create_signal('southdemo', ['Adopter'])
          
      
      
      def backwards(self, orm):
          
          # Deleting model 'Lizard'
          db.delete_table('southdemo_lizard')
          
          # Deleting model 'Adopter'
          db.delete_table('southdemo_adopter')
      
  
      
      models = { ... }
  
Migrations in South are, as you can see, just Migration classes with forwards()
and backwards() methods, which get run as you go forwards or backwards over the
migration respectively.

Each method gets an 'orm' parameter, which contains a 'fake ORM' - it will let
you access any frozen models for this migration (details on frozen models are
covered in part three of the tutorial).

Most of the time, you can get schemamigration to write either all or most of a
migration for you; continue to :ref:`part two of the tutorial <tutorial-part-2>`
for more about changing models.