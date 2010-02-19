
.. _tutorial-part-2:

Part 2: Model Changes
=====================

The core of a migrations library is making changes to models.
These are obviously accomplished through a migration, but there are several
ways to make a migration that changes the database schema:

 - Automatic detection of changes - South can examine the state of your models
   from the previous migration and the current state, and make a migration
   to match.
 - Explicitly telling startmigration what to add - using things like 
   ``--add-model`` and ``--add-field``.
 - Manually writing more advanced operations in Python.

All three will be covered here.

Automatic Detection
-------------------

South has automatic detection of changes - it can look at
the previous migration, and compare that with the current state of the models,
and make a migration to perform the necessary changes.

There are two caveats:

The whole app must be frozen previously
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The previous migration must have the entire application frozen onto it.
We will cover freezing in a bit more detail at the end of part 3, but for now
don't worry; South will ensure each migration automatically has their current
models frozen in, so autodetection will always just work.

It can't do everything
^^^^^^^^^^^^^^^^^^^^^^

It is impossible to detect renames of columns, for example; it looks like a
delete and an addition. Moreover, some detection features, such as changing
primary_key = True, are not yet handled. Some of these issues will be fixed in
future versions of South, but we can never detect everything accurately!

Autodetection is great for when you've added or removed a few fields in the
model, and want to migrate to that with only two commands (schemamigration and
then migrate). As with all migrations, you should look at what is created,
and check it is sane.

Automigrating
^^^^^^^^^^^^^

Now you understand the caveats, it's time to try it out. We'll take the same
app we used for part one.

Have another look at the migration file (``southdemo/migrations/0001_initial.py``) -
there is a large models dictionary on the bottom. If you look closely, it is a
representation of how your models are at the moment. It's using this stored
representation that allows South to see how your models change over time.

To illustrate this, we'll make a change; we'll add a field ``length`` to Lizard,
and allow the ``age`` to be left blank (and become null if it is).

Note that we **must** provide a default value for the length column, since we
are adding it to a table; the database has to know what to put in the empty new
cells. If the column has null=True set, it doesn't matter, as the cells will
default to NULL; in this case, though, we haven't specified null=True, and so
the new column defaults to NOT NULL.

(If you forget to specify a default, or don't want to specify one globally in
``models.py``, South (0.7 and up) will prompt you when you run
``schemamigration``, and allow you to manually enter a default just for use in
that migration.)

Here's the new ``models.py``::

 from django.db import models
 
 class Lizard(models.Model):
     
     age = models.IntegerField(null=True, blank=True)
     length = models.FloatField(default=-1)
     name = models.CharField(max_length=30)
 
 class Adopter(models.Model):
     
     lizard = models.ForeignKey(Lizard)
     name = models.CharField(max_length=50)

Now we've changed the models, we'll fire up the autodetector. The command is::

 ./manage.py schemamigration southdemo extend_lizard --auto

You should see this output, or something similar::

  + Added field 'southdemo.lizard.length'
  ~ Changed field 'southdemo.lizard.age'.
 Created 0002_extend_lizard.py.

Those small notifications are the quick summary of what South has detected;
if you trust it enough, and they look correct, you can proceed directly to
``./manage.py migrate southdemo``.

Thankfully, South is often correct, but in some cases it will pick up changes
you didn't want it to. When this happens, you want to open the resulting
migration, and remove the erroneous operations (remember to remove them from
the backwards() method, too) - don't worry, most will be commented with what
model changes they represent if you're not used to looking at migrations.

The changes you removed won't be redetected next time you run schemamigration;
the thing ``--auto`` compares with is that massive models dict at the bottom of
the migration file, not the actual operations, and if you look,
that will still have your changes in it.

If the process detected schema changes you didn't want to apply yet, rather 
than erroneous ones, then you should delete the new migration file, undo the
changes to your models you don't want migrated, and recreate it; there's
currently no way to select a subset of actions to include.

That's the quick summary of automigration; it's not perfect, so if you find any
bugs please use one of the support channels we have.

Explicit Operation
------------------

If you don't trust ``--auto``, or just like being in control, then the next-best
way of making migrations is to tell South what to do directly, via command-line
arguments.

To make migrations in this way, you call this to add a model::

 ./manage.py startmigration southdemo extend_lizard --add-model Country

and this to add a field to a model::

 ./manage.py startmigration southdemo extend_lizard --add-field Lizard.length

and this to add an index on a field to a model::

 ./manage.py startmigration southdemo extend_lizard --add-index Lizard.length

You can also combine these arguments, and use them more than once::

 ./manage.py startmigration southdemo extend_lizard --add-field Lizard.length --add-field Lizard.colour --model Country --model Species

Output is the same as --auto, but you can obviously only perform additions::

 $ ./manage.py startmigration southdemo extend_lizard --add-field Lizard.length
  + Added field 'southdemo.Lizard.length'
 Created 0003_extend_lizard.py.

If you want to create more complex migrations, or want to write field-removal
migrations without using autodetection, you'll have to resort to writing
migrations manually.

Manually writing migrations
---------------------------

Migrations are just Python classes with two methods, forwards and backwards.
The autodetector and even the ``--add-model`` and ``--add-field`` options are
simply helper functions; if you want to, you need never use them while using
South, although we strongly recommend that you do.

When you need to do more complex migrations - say, playing with indexes, or
swapping data between columns - you'll have to write it yourself. You're not
completely left out in the open, however; South offers two powerful tools
to the migration writer:

 - The :ref:`database-api`, which offers a convenient and database-agnostic API
   to common database manipulation commands.
 
 - The :ref:`ORM Freezer <orm-freezing>`, which allows you to access models from
   within migrations as they were at the time the migration was written.

ORM Freezing and other associated tricks will be covered in the next chapter.

The Database API is South's way for you to interact with the database. As well
as saving you from typing out all the SQL for ALTER TABLE, DROP COLUMN and
friends, it also offers as database-agnostic an API as possible; much like
Django itself, the correct SQL will be generated for the backend specified
in your settings.

Some database backends don't support some features (most notably SQLite),
but in general you can just change databases and everything will work - this is,
in fact, one of the main design decisions driving South's original creation
(the other driving decision being a library that knows when a migration
appears in the wrong place after a DVCS update).

There's an extensive :ref:`API reference <database-api>` with examples for each
command, to get you started. It's also recommended you take a look at migrations
that South has automatically created to get an idea of how they're written.

Finally, you can always turn to our mailing list, or #django-south on freenode
for help; there's usually someone helpful waiting to reply.

Changing the database is one side of the equation, but often a migration
involves changing data as well; for example, you're changing from a single
'password' field into separate 'salt' and 'hash' fields. It is at this point
you should turn to :ref:`part three <tutorial-part-3>`.
