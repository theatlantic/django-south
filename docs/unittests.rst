Unit Test Integration
=====================

By default, South's syncdb command will also apply migrations if it's run in
non-interactive mode, which includes when you're running tests - it will run
every migration every time you run your tests.

If you want the test runner to use syncdb instead of migrate - for example, if
your migrations are taking way too long to apply - simply set
``SOUTH_TESTS_MIGRATE = False`` in settings.py.

South's own unit tests
----------------------

South has its own set of unit tests, however, these will not be run by default
when you run ``./manage.py test``. This is mainly because the test suite is
meant to be run in isolation (the test framework continually changes
``INSTALLED_APPS`` and fiddles with the ORM as it runs, among other things),
and can cause compatability problems with other applications.

You can run South's test suite by setting ``SKIP_SOUTH_TESTS = False``
in settings.py, then running ``./manage.py test south``.
