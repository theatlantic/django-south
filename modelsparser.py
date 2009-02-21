"""
Parsing module for models.py files. Extracts information in a more reliable
way than inspect + regexes.
"""

import re
import inspect
import parser
import symbol
import token


def name_that_thing(thing):
    "Turns a symbol/token int into its name."
    for name in dir(symbol):
        if getattr(symbol, name) == thing:
            return "symbol.%s" % name
    for name in dir(token):
        if getattr(token, name) == thing:
            return "symbol.%s" % name
    return str(thing)


def thing_that_name(name):
    "Turns a name of a symbol/token into its integer value."
    if name in dir(symbol):
        return getattr(symbol, name)
    if name in dir(token):
        return getattr(token, name)
    raise ValueError("Cannot convert '%s'" % name)


def prettyprint(tree, indent=0, omit_singles=False):
    "Prettyprints the tree, with symbol/token names. For debugging."
    if omit_singles and isinstance(tree, tuple) and len(tree) == 2:
        return prettyprint(tree[1], indent, omit_singles)
    if isinstance(tree, tuple):
        return " (\n%s\n" % "".join([prettyprint(x, indent+1) for x in tree]) + \
            (" " * indent) + ")"
    elif isinstance(tree, int):
        return (" " * indent) + name_that_thing(tree)
    else:
        return " " + repr(tree)


class STTree(object):
    
    "A syntax tree wrapper class."
    
    def __init__(self, tree):
        assert isinstance(tree, tuple), "You must pass in a tree tuple."
        self.tree = tree
    
    
    @property
    def root(self):
        return self.tree[0]
    
    
    def tree_walk(self, recursive=True):
        "Yields (symbol, subtree) for the entire subtree."
        stack = [self.tree]
        done_outer = False
        while stack:
            atree = stack.pop()
            if isinstance(atree, tuple):
                if recursive or done_outer:
                    yield atree[0], atree
                if recursive or not done_outer:
                    for bit in atree[1:]:
                        stack.append(bit)
                    done_outer = True
    
    
    def findAllType(self, ntype, recursive=True):
        "Returns all nodes with the given type in the tree."
        for symbol, subtree in self.tree_walk(recursive=recursive):
            if symbol == ntype:
                yield STTree(subtree)
    
    
    def find(self, selector):
        """
        Searches the syntax tree with a CSS-like selector syntax.
        You can use things like 'suite simple_stmt', 'suite, simple_stmt'
        or 'suite > simple_stmt'.
        """
        # Split up the overall parts
        patterns = [x.strip() for x in selector.split(",")]
        results = []
        for pattern in patterns:
            # Split up the parts
            parts = re.split(r'(?:[\s]|(>))+', selector)
            # Take the first part, use it for results
            subresults = list(self.findAllType(thing_that_name(parts[0])))
            recursive = True
            # For each remaining part, do something
            for part in parts[1:]:
                if part == ">":
                    recursive = False
                elif not part:
                    pass
                else:
                    thing = thing_that_name(part)
                    newresults = [
                        list(tree.findAllType(thing, recursive))
                        for tree in subresults
                    ]
                    subresults = []
                    for stuff in newresults:
                        subresults.extend(stuff)
                    recursive = True
            results.extend(subresults)
        return results
    
    
    def __str__(self):
        return prettyprint(self.tree)
    __repr__ = __str__
    


def get_model_tree(model_instance):
    
    # Get the source of the model
    source = "".join(inspect.getsource(model_instance))
    return STTree(parser.suite(source).totuple())


def get_model_fields(model_instance):
    
    print tree.find("suite expr_stmt")

