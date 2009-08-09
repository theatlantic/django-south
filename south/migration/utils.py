from collections import deque

from django.utils.datastructures import SortedDict


def get_app_name(app):
    """
    Returns the _internal_ app name for the given app module.
    i.e. for <module django.contrib.auth.models> will return 'auth'
    """
    return app.__name__.split('.')[-2]

def flatten(*stack):
    stack = deque(stack)
    while stack:
        try:
            x = stack[0].next()
        except StopIteration:
            stack.popleft()
            continue
        if hasattr(x, '__iter__'):
            stack.appendleft(x)
        else:
            yield x

def _dfs(start, get_children):
    children = get_children(start)
    if children:
        # We need to apply all the migrations this one depends on
        yield (_dfs(n, get_children) for n in children)
    # Append ourselves to the result
    yield start

def dfs(start, get_children):
    return list(flatten(_dfs(start, get_children)))

def depends(start, get_children):
    result = SortedDict([(n, None) for n in dfs(start, get_children)])
    return list(result)
