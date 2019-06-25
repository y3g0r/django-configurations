import ast
import sys

from django.core.management.base import BaseCommand


class EnvVar:
    def __init__(self, node, prefix, name=None, default=None):
        self.name = name
        self.prefix = prefix
        self.node = node
        self.default = default

    def __str__(self):
        return "{}_{}".format(self.prefix, self.name)

    def __repr__(self):
        return str(self)

class NodeVisitor(object):
    """
    A node visitor base class that walks the abstract syntax tree and calls a
    visitor function for every node found.  This function may return a value
    which is forwarded by the `visit` method.

    This class is meant to be subclassed, with the subclass adding visitor
    methods.

    Per default the visitor functions for the nodes are ``'visit_'`` +
    class name of the node.  So a `TryFinally` node visit function would
    be `visit_TryFinally`.  This behavior can be changed by overriding
    the `visit` method.  If no visitor function exists for a node
    (return value `None`) the `generic_visit` visitor is used instead.

    Don't use the `NodeVisitor` if you want to apply changes to nodes during
    traversing.  For this a special visitor exists (`NodeTransformer`) that
    allows modifications.
    """
    def traverse(self, tree):
        for _ in self.visit(tree):
            pass

    def visit(self, node):
        """Visit a node."""
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        yield from visitor(node)

    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        yield from self.visit(item)
            elif isinstance(value, ast.AST):
                yield from self.visit(value)

VALUES_CLASSES = {
    'Value',
    'BooleanValue',
    'IntegerValue',
    'PositiveIntegerValue',
    'FloatValue',
    'DecimalValue',
    'SequenceValue',
    'ListValue',
    'TupleValue',
    'SingleNestedSequenceValue',
    'SingleNestedListValue',
    'SingleNestedTupleValue',
    'BackendsValue',
    'SetValue',
    'DictValue',
    'EmailValue',
    'URLValue',
    'IPValue',
    'RegexValue',
    'PathValue',
    'SecretValue',
    'EmailURLValue',
    'DictBackendMixin',
    'DatabaseURLValue',
    'CacheURLValue',
    'SearchURLValue',
}


class ValuesFetcher(NodeVisitor):
    def __init__(self):
        self._variables = []

    @property
    def variables(self):
        return self._variables

    def visit_Assign(self, node):
        for env_var in self.generic_visit(node):
            if env_var:
                env_var.name = node.targets[0].id
                self._variables.append(env_var)
                yield

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            # TODO: check that the name is actually coming from 'values' python package
            if node.func.id in VALUES_CLASSES:
                pass
        elif isinstance(node.func, ast.Attribute):
            if node.func.value.id == 'values' and node.func.attr in VALUES_CLASSES:
                pass
        else:
            return

        env_var = EnvVar(prefix='DJANGO', node=node)
        for keyword in node.keywords:
            if keyword.arg == 'environ':
                if keyword.value.value == 'False':
                    return
            elif keyword.arg == 'environ_prefix':
                # TODO: assuming that kwarg value is literal string
                env_var.prefix = keyword.value.s
            elif keyword.arg == 'environ_name':
                # TODO: assuming that kwarg value is literal string
                env_var.name = keyword.value.s
        if env_var.name:
            self._variables.append(env_var)
        else:
            yield env_var


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('-i', '--input')

    def handle(self, *args, **options):
        settings_file = options['input']
        parsed_settings = self.process(settings_file)
        printable_dump = self.dump(parsed_settings)
        self.stdout.write(printable_dump)

    def process(self, settings_file):
        content = self._read_file(settings_file)
        return self._parse(content)

    @staticmethod
    def _read_file(file_name):
        if file_name:
            with open(file_name) as f:
                return f.read()
        else:
            return sys.stdin.read()

    @staticmethod
    def _parse(settings_file_content):
        return ast.parse(settings_file_content)

    @staticmethod
    def dump(parsed_settings):
        # input: KEY = values.Value(environ_name='DEBUG')  output: export DJANGO_DEBUG=
        # input: KEY = values.Value()  output: export DJANGO_KEY=
        # input: KEY = values.Value(True)  output: # export DJANGO_KEY=true
        # input: KEY = values.DictValue({1:2}])  output: # export DJANGO_KEY={1:2}
        #
        # variable = 'SECRET_KEY'
        # input: KEY = values.Value(environ_name=variable)  output: export DJANGO_SECRET_KEY=
        # KEY = values.Values(environ_name='KEY', environ_prefix='DJANGO')
        # from configurations.values import Value

        # 1) find *values.*
        # 2) check keyword argument environ is not False
        # 3) environment variable name digging:
        #    - check environ_prefix
        #    - check environ_name
        #    - use variable name from assignment
        return ''

