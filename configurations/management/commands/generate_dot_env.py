import ast
import sys

import astor
from django.core.management.base import BaseCommand

from configurations.generate_dot_env_utils import ValuesVisitor, EnvVarFormatter, AssignCollector


class EnvVar:
    def __init__(self, environ_name=None, environ_prefix='DJANGO', default=None, tree=None, cls_name='Value'):
        self._environ_name = environ_name
        self._environ_prefix = environ_prefix
        self._default = default
        self._tree = tree
        self._cls_name = cls_name

    @property
    def environ_name(self):
        try:
            return self._environ_name()
        except TypeError:
            return self._environ_name

    @property
    def environ_prefix(self):
        try:
            return self._environ_prefix()
        except TypeError:
            return self._environ_prefix

    @property
    def default(self):
        try:
            return self._default()
        except TypeError:
            return self._default

    @property
    def name(self):
        return self.environ_prefix + '_' + self.environ_name

    @property
    def spec(self):
        spec_line = "{type}{default}"
        type = 'Type: ' + self.type
        _default = self.default
        if _default:
            default = ', Default: ' + _default
        else:
            default = ''
        return spec_line.format(type=type, default=default)

    @property
    def type(self):
        if self._cls_name == 'Value':
            return 'String'
        else:
            return self._cls_name[:-len('Value')]

    @property
    def extra(self):
        return ''

    def set_positional(self, pos, node):
        if pos == 0:
            self._set_default(node)
        else:
            raise Exception('Unknown positional argument. Position: {}, Value: {}'.format(pos, node))

    def set_keyword(self, keyword, node):
        if keyword == 'default':
            self._set_default(node)
        elif keyword == 'environ_name':
            self._set_environ_name(node)
        elif keyword == 'environ_prefix':
            self._set_environ_prefix(node)
        elif keyword == 'environ_required':
            pass
        else:
            raise Exception('''Unknown keyword argument. Keyword: '{}', value: {}'''.format(keyword, node))

    def _set_environ_name(self, node):
        """
        KEY = values.Value()    : node is Name(identifier id, expr_context ctx), id=KEY, ctx=Store
        KEY = values.Value(environ_name='FOO')  : node is Str(string s), s=FOO
        bar='BAR'; KEY=values.Value(environ_name=bar)   : node is Name, id=bar, ctx=Load

        :param node:
        :type node: ast.Name or ast.Str
        :return:
        """
        if isinstance(node, ast.Str):
            self._environ_name = node.s
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                self._environ_name = node.id
            elif isinstance(node.ctx, ast.Load):
                resolved_name = self._resolve_variable(node, tree=self._tree)
                if resolved_name:
                    self._environ_name = resolved_name
                else:
                    raise Exception("Can't resolve variable {}".format(ast.dump(node)))

        if not self._environ_name:
            raise Exception("Unknown node type: {}".format(ast.dump(node)))

    def _set_environ_prefix(self, node):
        if isinstance(node, ast.Str):
            self._environ_prefix = node.s
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            resolved_prefix = self._resolve_variable(node, tree=self._tree)
            if resolved_prefix:
                self._environ_prefix = resolved_prefix
            else:
                raise Exception("Can't resolve variable {}".format(ast.dump(node)))

        if not self._environ_prefix:
            raise Exception("Unknown node type: {}".format(ast.dump(node)))

    def _set_default(self, default_node):
        if isinstance(default_node, ast.Name):
            for node in ast.walk(self._tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == default_node.id:
                            self._default = 'Variable: ' + astor.to_source(node).strip()
        else:
            self._default = self._node_to_source(default_node)

    def _resolve_variable(self, variable_node, tree=None, depth=3):
        """
        Attempts to
        :param variable_node:
        :type variable_node: ast.Name
        :param depth: how deep to recursively try to resolve variable.
                     For example:
                        a = 1
                        b = a
                        c = b
                        _resolve_variable(c, depth=0) == b
                        _resolve_variable(c, depth=1) == a
                        _resolve_variable(c, depth=99999) == 1
        """
        if not tree:
            raise Exception("Can not resolve variable {}. AST tree is not provided or empty.".format(
                ast.dump(variable_node)
            ))

        # TODO: This is naive! Need to consider different scopes!
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == variable_node.id:
                        if isinstance(node.value, ast.Name) and depth:
                            return self._resolve_variable(node.value, tree, depth=depth-1)
                        else:
                            return self._node_to_source(node.value)

    def _node_to_source(self, node):
        if isinstance(node, ast.Str):
            return node.s
        if isinstance(node, ast.Num):
            return str(node.n)
        else:
            return astor.to_source(node).strip()

    def __str__(self):
        line = "{prefix}_{name}".format(prefix=self.environ_prefix, name=self.environ_name)
        default = self.default
        if default:
            line = "{name}={default}".format(name=line, default=default)
        return line

    def __repr__(self):
        return str(self)


class RegexEnvVar(EnvVar):
    def __init__(self, regex=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._regex = regex

    def set_keyword(self, keyword, node):
        if keyword == 'regex':
            self._regex = self._node_to_source(node)
        else:
            super().set_keyword(keyword=keyword, node=node)

    def set_positional(self, pos, node):
        if pos == 1:
            self._regex = self._node_to_source(node)
        else:
            super().set_positional(pos=pos, node=node)

    @property
    def extra(self):
        line = super().extra
        return line + ' (regex={})'.format(self._regex)


class PathEnvVar(EnvVar):
    def __init__(self, checks_exists=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checks_exists = checks_exists

    def set_keyword(self, keyword, node):
        if keyword == 'checks_exists':
            self._checks_exists = self._node_to_source(node)
        else:
            super().set_keyword(keyword=keyword, node=node)

    @property
    def extra(self):
        line = super().extra
        return line + ' (checks_exists={})'.format(self._checks_exists)


class ListEnvVar(EnvVar):
    empty_default = '[]'

    def __init__(self, separator=',', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._separator = separator

    def _node_to_source(self, node):
        if isinstance(node, ast.List) \
                or isinstance(node, ast.Tuple) \
                or isinstance(node, ast.Set):
            dump = []
            for element in node.elts:
                dump.append(super()._node_to_source(element))
            if not dump:
                return self.empty_default
            else:
                return self._separator.join(dump)
        else:
            return super()._node_to_source(node)

    def set_keyword(self, keyword, node):
        if keyword == 'separator':
            self._separator = self._node_to_source(node)
        else:
            super().set_keyword(keyword=keyword, node=node)

    @property
    def extra(self):
        line = super().extra
        return line + ' (separator={})'.format(self._separator)


class TupleEnvVar(ListEnvVar):
    empty_default = '()'


class SetEnvVar(ListEnvVar):
    empty_default = '{}'


class SingleNestedListEnvVar(ListEnvVar):
    def __init__(self, seq_separator=';', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._seq_separator = seq_separator

    def _node_to_source(self, node):
        if isinstance(node, ast.List) \
                or isinstance(node, ast.Tuple):
            dump = []
            for element in node.elts:
                dump.append(super()._node_to_source(element))
            if not dump:
                return self.empty_default
            else:
                return self._seq_separator.join(dump)
        else:
            return super()._node_to_source(node)

    def set_keyword(self, keyword, node):
        if keyword == 'seq_separator':
            self._seq_separator = self._node_to_source(node)
        else:
            super().set_keyword(keyword=keyword, node=node)

    @property
    def extra(self):
        line = super().extra
        return line + ' (seq_separator={})'.format(self._seq_separator)


class SingleNestedTupleEnvVar(SingleNestedListEnvVar):
    empty_default = '()'


VALUES_CLASSES_TO_ENV_VAR = {
    'ListValue': ListEnvVar,
    'TupleValue': TupleEnvVar,
    'SingleNestedListValue': SingleNestedListEnvVar,
    'SingleNestedTupleValue': SingleNestedTupleEnvVar,
    'SetValue': SetEnvVar,
    'RegexValue': RegexEnvVar,
    'PathValue': PathEnvVar,
    'BackendsValue': ListEnvVar,
}


def env_var_factory(cls_name, **kwargs):
    env_var_cls = VALUES_CLASSES_TO_ENV_VAR.get(cls_name, EnvVar)
    return env_var_cls(**kwargs, cls_name=cls_name)


VALUE_CLASSES = [
    'Value',
    'BooleanValue',
    'IntegerValue',
    'PositiveIntegerValue',
    'FloatValue',
    'DecimalValue',
    'ListValue',
    'TupleValue',
    'SingleNestedListValue',
    'SingleNestedTupleValue',
    'SetValue',
    'DictValue',
    'EmailValue',
    'URLValue',
    'IPValue',
    'RegexValue',
    'PathValue',
    'DatabaseURLValue',
    'CacheURLValue',
    'EmailURLValue',
    'SearchURLValue',
    'BackendsValue',
    'SecretValue',
]


# noinspection PyPep8Naming
class CustomisableVariablesFinder(ast.NodeVisitor):
    def __init__(self, tree):
        self._tree = tree
        self._variables = None
        self._noname = None

    def traverse(self):
        self.visit(self._tree)

    @property
    def variables(self):
        if self._variables is None:
            self._variables = []
            self.traverse()
        return self._variables

    def visit_Assign(self, node):
        self.generic_visit(node)
        if self._noname:
            variable = self._noname
            self._noname = None
            variable.set_keyword('environ_name', node.targets[0])
            self._variables.append(variable)

    def visit_Call(self, node):
        """Call(expr func, expr* args, keyword* keywords)

        keyword = (identifier? arg, expr value)
        """
        cls_name = self._values_cls_name(node.func)
        if not cls_name:
            return
        env_var = env_var_factory(cls_name=cls_name, tree=self._tree)
        for kwarg in node.keywords:
            if kwarg.arg == 'environ' and kwarg.value.value is False:
                return
            env_var.set_keyword(kwarg.arg, kwarg.value)
        for pos, arg in enumerate(node.args):
            env_var.set_positional(pos, arg)

        if env_var.environ_name:
            self._variables.append(env_var)
        else:
            self._noname = env_var

    @staticmethod
    def _values_cls_name(func_node):
        name = CustomisableVariablesFinder._callable_name(func_node)
        if name in VALUE_CLASSES:
            return name

    @staticmethod
    def _callable_name(func_node):
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            return func_node.attr
        else:
            raise Exception("Don't know how to get class name from {}".format(ast.dump(func_node)))

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
            try:
                return sys.stdin.read()
            except (EOFError, KeyboardInterrupt):
                sys.exit(1)

    @staticmethod
    def _parse(settings_file_content):
        return ast.parse(settings_file_content)

    @staticmethod
    def dump_single_variable(variable):
        return "export {name}=".format(name=variable.name)

    @staticmethod
    def dump_single_variable_comment(variable):
        line ="# {name}{type}{default}{extra}"
        name = variable.name
        type = ': ' + variable.type
        _default = variable.default
        if _default:
            default = '=' + _default
        else:
            default = ''
        extra = variable.extra
        return line.format(name=name, type=type, default=default, extra=extra)

    @staticmethod
    def dump(parsed_settings, sort=False):
        finder = CustomisableVariablesFinder(parsed_settings)

        result = []
        for variable in finder.variables:
            result.append(Command.dump_single_variable_comment(variable))
            result.append(Command.dump_single_variable(variable))

        return '\n'.join(result)