"""
Parsing module for models.py files. Extracts information in a more reliable
way than inspect + regexes.
"""

import re
import inspect
import parser
import symbol
import token
import keyword


def name_that_thing(thing):
    "Turns a symbol/token int into its name."
    for name in dir(symbol):
        if getattr(symbol, name) == thing:
            return "symbol.%s" % name
    for name in dir(token):
        if getattr(token, name) == thing:
            return "token.%s" % name
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
        self.tree = tree
    
    
    @property
    def root(self):
        return self.tree[0]
    
    
    @property
    def value(self):
        return self.tree
    
    
    def flatten(self, recursive=True):
        """
        Yields (symbol, subtree) for the entire subtree.
        Comes out in reverse lexical order, until my brain unmelts enough.
        """
        stack = [self.tree]
        done_outer = False
        while stack:
            atree = stack.pop()
            if isinstance(atree, tuple):
                if recursive or done_outer:
                    yield atree[0], STTree(atree)
                if recursive or not done_outer:
                    for bit in atree[1:]:
                        stack.append(bit)
                    done_outer = True
    
    
    def findAllType(self, ntype, recursive=True):
        "Returns all nodes with the given type in the tree."
        for symbol, subtree in self.flatten(recursive=recursive):
            if symbol == ntype:
                yield subtree
    
    
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
            if parts[0] == "^":
                subresults = [self]
            else:
                subresults = list(self.findAllType(thing_that_name(parts[0])))
            recursive = True
            # For each remaining part, do something
            for part in parts[1:]:
                if not subresults:
                    break
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
    # Get the source of the model's file
    source = open(inspect.getsourcefile(model_instance)).read()
    tree = STTree(parser.suite(source).totuple())
    
    # Now, we have to find it
    for poss in tree.find("compound_stmt"):
        if poss.value[1][0] == symbol.classdef and \
           poss.value[1][2][1] == model_instance.__name__:
            # This is the tree
            return poss


token_map = {
    token.DOT: ".",
    token.LPAR: "(",
    token.RPAR: ")",
    token.EQUAL: "=",
    token.EQEQUAL: "==",
    token.COMMA: ",",
    token.LSQB: "[",
    token.RSQB: "]",
    token.AMPER: "&",
    token.BACKQUOTE: "`",
    token.CIRCUMFLEX: "^",
    token.CIRCUMFLEXEQUAL: "^=",
    token.COLON: ":",
    token.DOUBLESLASH: "//",
    token.DOUBLESLASHEQUAL: "//=",
    token.DOUBLESTAR: "**",
    token.DOUBLESLASHEQUAL: "**=",
    token.GREATER: ">",
    token.LESS: "<",
    token.GREATEREQUAL: ">=",
    token.LESSEQUAL: "<=",
    token.LBRACE: "{",
    token.RBRACE: "}",
    token.SEMI: ";",
    token.PLUS: "+",
    token.MINUS: "-",
    token.STAR: "*",
    token.SLASH: "/",
    token.VBAR: "|",
    token.PERCENT: "%",
    token.TILDE: "~",
    token.AT: "@",
    token.NOTEQUAL: "!=",
    token.LEFTSHIFT: "<<",
    token.RIGHTSHIFT: ">>",
    token.LEFTSHIFTEQUAL: "<<=",
    token.RIGHTSHIFTEQUAL: ">>=",
    token.PLUSEQUAL: "+=",
    token.MINEQUAL: "-=",
    token.STAREQUAL: "*=",
    token.SLASHEQUAL: "/=",
    token.VBAREQUAL: "|=",
    token.PERCENTEQUAL: "%=",
    token.AMPEREQUAL: "&=",
}


def reform(bits):
    "Returns the string that the list of tokens/symbols 'bits' represents"
    output = ""
    for bit in bits:
        if bit in token_map:
            output += token_map[bit]
        elif bit[0] in [token.NAME, token.STRING, token.NUMBER]:
            if keyword.iskeyword(bit[1]):
                output += " %s " % bit[1]
            else:
                output += bit[1]
    return output


def extract_field(tree):
    # Collapses the tree and tries to parse it as a field def
    bits = []
    for sym, subtree in reversed(list(tree.flatten())):
        if sym in token_map:
            bits.append(sym)
        elif sym == token.NAME:
            bits.append(subtree.value)
        elif sym == token.STRING:
            bits.append(subtree.value)
        elif sym == token.NUMBER:
            bits.append(subtree.value)
    # Check it looks right
    if len(bits) < 2 or bits[1] != token.EQUAL:
        return
    # OK, extract and reform it
    return bits[0][1], reform(bits[2:])
    


def get_model_fields(model_instance):
    
    tree = get_model_tree(model_instance)
    possible_field_defs = tree.find("^ > classdef > suite > stmt > simple_stmt > small_stmt > expr_stmt")
    fields = {}
    
    for pfd in possible_field_defs:
        field = extract_field(pfd)
        if field:
            fields[field[0]] = field[1]
    
    return fields

