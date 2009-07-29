def get_app_name(app):
    """
    Returns the _internal_ app name for the given app module.
    i.e. for <module django.contrib.auth.models> will return 'auth'
    """
    return app.__name__.split('.')[-2]


def get_app_fullname(app):
    """
    Returns the full python name of an app - e.g. django.contrib.auth
    """
    return '.'.join(app.__name__.split('.')[:-1])


