"""
Python 2 + 3 compatibility functions. This is a very small subset of six.
"""

import sys

PY3 = sys.version_info[0] == 3

if PY3:
    string_types = str,
    text_type = str

else:
    string_types = basestring,
    text_type = unicode
