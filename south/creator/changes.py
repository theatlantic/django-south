"""
Contains things to detect changes - either using options passed in on the
commandline, or by using autodetection, etc.
"""


class ManualChanges(object):
    """
    Detects changes by reading the command line.
    """
    
    def __init__(self, current_orm):
        self.current_orm = current_orm
    
    def get_changes(self):
        return [
            ("AddModel", {"model": self.current_orm['books.Book']}),
        ]