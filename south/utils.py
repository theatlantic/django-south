"""
Generally helpful utility functions.
"""


def ask_for_it_by_name(name):
    "Returns an object referenced by absolute path."
    bits = name.split(".")
    modulename = ".".join(bits[:-1])
    module = __import__(modulename, {}, {}, bits[-1])
    return getattr(module, bits[-1])


def get_attribute(item, attribute):
    """
    Like getattr, but recursive (i.e. you can ask for 'foo.bar.yay'.)
    """
    value = item
    for part in attribute.split("."):
        value = getattr(value, part)
    return value


fst = lambda (x, y): x
snd = lambda (x, y): y