Database API
============

South ships with a full database-agnostic API for performing schema changes
on databases, much like Django's ORM provides data manipulation support.

Currently, South supports:

 - PostgreSQL
 - MySQL
 - SQLite
 - Microsoft SQL Server (beta support)
 - Oracle (alpha support)
 
Methods
-------

These are how you perform changes on the database. See "Accessing The API" below
to see where these run.


Accessing The API
-----------------

South automatically exposes the correct set of database API operations as
``south.db.db``; it detects which database backend you're using from your
Django settings file.

If you're using multiple database support (Django 1.2 and higher),
there's a corresponding ``south.db.dbs`` dictionary
which contains a DatabaseOperations object (the object which has the methods
defined above) for each database alias in your configuration file.
