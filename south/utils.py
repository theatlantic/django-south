"""
Generally helpful utility functions.
"""


def _ask_for_it_by_name(name):
    "Returns an object referenced by absolute path."
    bits = name.split(".")

    ## what if there is no absolute reference?
    if len(bits)>1:
        modulename = ".".join(bits[:-1])
    else:
        modulename=bits[0]
        
    module = __import__(modulename, {}, {}, bits[-1])
    return getattr(module, bits[-1])


def ask_for_it_by_name(name): 
    "Returns an object referenced by absolute path. (Memoised outer wrapper)"
    if name not in ask_for_it_by_name.cache: 
        ask_for_it_by_name.cache[name] = _ask_for_it_by_name(name) 
    return ask_for_it_by_name.cache[name] 
ask_for_it_by_name.cache = {} 


def get_attribute(item, attribute):
    """
    Like getattr, but recursive (i.e. you can ask for 'foo.bar.yay'.)
    """
    value = item
    for part in attribute.split("."):
        value = getattr(value, part)
    return value


def has_spatialite():
    try:
        from ctypes.util import find_library
    except ImportError:
        return False
    from django.conf import settings
    return bool(getattr(settings, 'SPATIALITE_LIBRARY_PATH', find_library('spatialite')))


fst = lambda (x, y): x
snd = lambda (x, y): y
