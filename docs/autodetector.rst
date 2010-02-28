
.. _autodetector:

The Autodetector
================

The autodetector is the part of South you'll probably be using the most, as well
as being the feature that people seem to like the most.

The general use of the autodetector is covered in :ref:`tutorial-part-1`; this
is more of a reference of what it's capable of.

When the autodetector runs, it compares your current models with those frozen
in your most recent migration on the app, and if it finds any changes, yields
one or more Actions to the South migration-file-writer.

.. _autodetector-supported-actions:

Supported Actions
-----------------

Model creation and deletion
^^^^^^^^^^^^^^^^^^^^^^^^^^^

South will happily detect the creation and deletion of models; this is the
oldest and most well-worn feature of the autodetector, and so has very few
caveats.

One thing to note is that, while South calls the post_syncdb hook on your
models (much like ``syncdb`` does), it calls it when it initially creates the
table, not at the end of the migration, so your hook might well get called
when the model doesn't have its full table.

Consider moving your hook code into its own data migration, or use one of
our own :ref:`signals`.

Field addition and removal
^^^^^^^^^^^^^^^^^^^^^^^^^^

South detects addition and removal of fields fine, and should correctly create
indexes and constraints for new fields.

Note that when you add or remove a field, you need a default specified; there's
more explanation on this in the :ref:`tutorial-part-2-defaults` part of the
tutorial.



