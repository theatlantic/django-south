"""
Temporary South module while we move directory structure.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
print >> sys.stderr, "Depreciation warning: South has now moved to the south/ subdirectory. You will need to reconfigure your svn:external or library paths in your application."
del sys.modules['south']
import south
