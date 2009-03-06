import unittest

from south.db import db
from south.tests import Monkeypatcher


class TestModelParsing(Monkeypatcher):

    """
    Tests parsing of models.py files against the test one.
    """
    
    def test_fakeapp_modelspy(self):
        pass