
.. _tutorial-part-3:

Part 3: Advanced Commands
=========================

Listing current migrations
--------------------------

It can be very useful to know what migrations you currently have applied, and
which ones are available. For this reason, there's ``./manage.py migrate --list``.

Run against our project from before, we get::

 $ ./manage.py migrate --list

 southtut
  (*) 0001_initial
  (*) 0002_auto__add_field_knight_dances_whenever_able
  (*) 0003_auto__add_field_knight_shrubberies
  (*) 0004_auto__add_unique_knight_name
  
The output has an asterisk ``(*)`` next to a migration name if it has been
applied, and an empty space ``( )`` if not.
 
If you have a lot of apps or migrations, you can also specify an app name
to show just the migrations from that app.

Data migrations
---------------

TODO