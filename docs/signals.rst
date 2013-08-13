
.. _signals:

Signals
=======

South offers its own signals, if you want to write code which executes before
or after migrations. They're available from ``south.signals``.


pre_migrate
-----------

Sent just before South starts running migrations for an app.

Provides the following arguments,
    ``app``
        a string containing the app's label.

    ``verbosity``
        Indicates how much information manage.py is printing on screen. See the --verbosity flag for details.
        Functions which listen for pre_migrate should adjust what they output to the screen based on the value of this argument.

    ``interactive``
        If interactive is True, it’s safe to prompt the user to input things on the command line.
        If interactive is False, functions which listen for this signal should not try to prompt for anything.

    ``db``
        The alias of database on which a command will operate.


post_migrate
------------

Sent just after South successfully finishes running migrations for an app. Note
that if the migrations fail in the middle of executing, this will not get called.

Provides the following arguments,
    ``app``
        a string containing the app's label.

    ``verbosity``
        Indicates how much information manage.py is printing on screen. See the --verbosity flag for details.
        Functions which listen for pre_migrate should adjust what they output to the screen based on the value of this argument.

    ``interactive``
        If interactive is True, it’s safe to prompt the user to input things on the command line.
        If interactive is False, functions which listen for this signal should not try to prompt for anything.

    ``db``
        The alias of database on which a command will operate.


ran_migration
------------

Sent just after South successfully runs a single migration file; can easily be
sent multiple times in one run of South, possibly hundreds of times if you
have hundreds of migrations, and are doing a fresh install.

Provides the following arguments,
    ``app``
        a string containing the app's label.

    ``migration``
        a Migration object,

    ``method``
        Either ``"forwards"`` or ``"backwards"``.

    ``verbosity``
        Indicates how much information manage.py is printing on screen. See the --verbosity flag for details.
        Functions which listen for pre_migrate should adjust what they output to the screen based on the value of this argument.

    ``interactive``
        If interactive is True, it’s safe to prompt the user to input things on the command line.
        If interactive is False, functions which listen for this signal should not try to prompt for anything.

    ``db``
        The alias of database on which a command will operate.