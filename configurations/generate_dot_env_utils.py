import ast
import astor


class EnvVar:
    def __init__(self, environ_name=None, environ_prefix='DJANGO', default=None, tree=None, cls_name='Value'):
        self.environ_name = environ_name
        self.environ_prefix = environ_prefix
        self.default = default
        self._tree = tree
        self._cls_name = cls_name

    @property
    def name(self):
        return self.environ_prefix + '_' + self.environ_name

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
        elif keyword in {'environ_required', 'alias', 'converter'}:
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
        name = None
        if isinstance(node, ast.Str):
            name = node.s
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                name = node.id
            elif isinstance(node.ctx, ast.Load):
                resolved_name = self._resolve_variable(node, tree=self._tree)
                if resolved_name:
                    name = resolved_name
                else:
                    raise Exception("Can't resolve variable {}".format(ast.dump(node)))

        if name:
            self.environ_name = name
        else:
            raise Exception("Unknown node type: {}".format(ast.dump(node)))

    def _set_environ_prefix(self, node):
        prefix = None
        if isinstance(node, ast.Str):
            prefix = node.s
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            resolved_prefix = self._resolve_variable(node, tree=self._tree)
            if resolved_prefix:
                prefix = resolved_prefix
            else:
                raise Exception("Can't resolve variable {}".format(ast.dump(node)))

        if prefix:
            self.environ_prefix = prefix
        else:
            raise Exception("Unknown node type: {}".format(ast.dump(node)))

    def _set_default(self, default_node):
        default = None
        if isinstance(default_node, ast.Name):
            for node in ast.walk(self._tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == default_node.id:
                            default = 'Variable: ' + astor.to_source(node).strip()
        else:
            default = self._node_to_source(default_node)
        self.default = default

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
        line = "# {name}{type}{default}{extra}"
        name = self.name
        type = ': ' + self.type
        _default = self.default
        if _default:
            default = '=' + _default
        else:
            default = ''
        extra = self.extra
        return line.format(name=name, type=type, default=default, extra=extra)

    __repr__ = __str__


class _EnvVarWithExtra(EnvVar):
    _extra_params = {}     # name: default

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._extra = {}
        for name, default in self._extra_params.items():
            self._extra[name] = kwargs.get(name, default)

    def set_keyword(self, keyword, node):
        if keyword in self._extra:
            self._extra[keyword] = self._node_to_source(node)
        else:
            super().set_keyword(keyword=keyword, node=node)

    @property
    def extra(self):
        line = super().extra
        for name, value in self._extra.items():
            line += ' ({param}={value})'.format(param=name, value=value)
        return line


class RegexEnvVar(_EnvVarWithExtra):
    _extra_params = {'regex': None}

    def set_positional(self, pos, node):
        if pos == 1:
            self._extra['regex'] = self._node_to_source(node)
        else:
            super().set_positional(pos=pos, node=node)


class PathEnvVar(_EnvVarWithExtra):
    _extra_params = {'checks_exists': True}


class ListEnvVar(_EnvVarWithExtra):
    empty_default = '[]'
    _extra_params = {'separator': ','}

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
                return self._extra['separator'].join(dump)
        else:
            return super()._node_to_source(node)


class TupleEnvVar(ListEnvVar):
    empty_default = '()'


class SetEnvVar(ListEnvVar):
    empty_default = '{}'


class SingleNestedListEnvVar(ListEnvVar):
    _extra_params = {
        'separator': ',',
        'seq_separator': ';'
    }

    def _node_to_source(self, node):
        if isinstance(node, ast.List) \
                or isinstance(node, ast.Tuple):
            dump = []
            for element in node.elts:
                dump.append(super()._node_to_source(element))
            if not dump:
                return self.empty_default
            else:
                return self._extra['seq_separator'].join(dump)
        else:
            return super()._node_to_source(node)


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
    return env_var_cls(cls_name=cls_name, **kwargs)


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

    def traverse(self, tree=None):
        self._variables = []
        if tree:
            self._tree = tree
        self.visit(self._tree)

    @property
    def variables(self):
        if self._variables is None:
            self.traverse()
        return self._variables

    def visit_Assign(self, node):
        self.generic_visit(node)
        if self._noname:
            variable = self._noname
            self._noname = None
            variable.set_keyword('environ_name', node.targets[0])
            self.variables.append(variable)

    def visit_Call(self, node):
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
            self.variables.append(env_var)
        else:
            self._noname = env_var

    @staticmethod
    def _values_cls_name(func_node):
        if isinstance(func_node, ast.Name):
            name = func_node.id
        elif isinstance(func_node, ast.Attribute):
            name = func_node.attr
        else:
            raise Exception("Don't know how to get class name from {}".format(ast.dump(func_node)))

        if name in VALUE_CLASSES:
            return name
