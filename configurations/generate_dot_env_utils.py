import ast
import functools
import json
import re

import astor


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


# noinspection PyPep8Naming
class AssignCollector(ast.NodeVisitor):
    def __init__(self):
        self.assignments = {}

    def traverse(self, tree):
        self.visit(tree)
        return self.assignments

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.assignments[target.id] = node.value


# noinspection PyPep8Naming
class ValuesVisitor(NodeVisitor):
    def __init__(self):
        self.variables = []

    def traverse(self, tree):
        for _ in self.visit(tree):
            pass
        return self.variables

    def visit_Assign(self, node):
        for env_var in self.generic_visit(node):
            if env_var:
                env_var.environ_name = node.targets[0].id
                self.variables.append(env_var)
                yield

    def visit_Call(self, node):
        cls_name = self._get_values_cls_name(node.func)
        if not cls_name:
            yield from self.generic_visit(node)
            return

        env_var = env_variable_factory(cls_name=cls_name, node=node)
        for keyword in node.keywords:
            if keyword.arg == 'environ':
                if keyword.value.value is False:
                    return
            setattr(env_var, keyword.arg, keyword.value)

        for pos, arg in enumerate(node.args):
            env_var.store_positional_arg(pos, arg)

        if env_var.environ_name:
            self.variables.append(env_var)
        else:
            yield env_var

    @staticmethod
    def _get_values_cls_name(node):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == 'values':
                name = node.attr

        if name in VALUES_CLASSES:
            return name


class EnvVar:
    def __init__(self, node, environ_prefix='DJANGO', environ_name=None, default=None, cls_name='Value'):
        self.environ_name = environ_name
        self.environ_prefix = environ_prefix
        self.node = node
        self.default = default
        self.values_cls_name = cls_name

    def store_positional_arg(self, pos, value):
        if pos == 0:
            self.default = value
        else:
            raise Exception('Unknown positional argument. Position: {}, value: {}'.format(pos, ast.dump(value)))

    def _str_default(self):
        return self.default

    def _extra_strings(self):
        return []

    def __str__(self):
        full_name = "{}_{}".format(self.environ_prefix, self.environ_name)
        default_value = self._str_default()
        extra = self._extra_strings()

        full_string = full_name

        if default_value:
            full_string += "={}".format(default_value)
        if extra:
            full_string += ' ({})'.format((', '.join(extra)))

        return full_string

    def __repr__(self):
        return "EnvVar(prefix={!r}, name={!r}, default={!r})".format(
            self.environ_prefix,
            self.environ_name,
            self.default
        )


class BooleanEnvVar(EnvVar):
    def _str_default(self):
        if self.default:
            return 'true'
        else:
            return 'false'


class RegexEnvVar(EnvVar):
    def __init__(self, regex=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regex = regex

    def _extra_strings(self):
        return ['regex: {}'.format(self.regex)]

    def store_positional_arg(self, pos, value):
        if pos == 1:
            self.regex = value
        else:
            super().store_positional_arg(pos, value)


class SequenceEnvVar(EnvVar):
    def __init__(self, separator=',', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.separator = separator

    def _str_default(self):
        return self.default and self.default\
                    .replace(',', self.separator)\
                    .replace('(', '')\
                    .replace(')', '')\
                    .replace("'", "")


class NestedSequenceEnvVar(SequenceEnvVar):
    def __init__(self, seq_separator=';', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seq_separator = seq_separator

    def _str_default(self):
        translate_table = {
            '),(': self.seq_separator,
            '],[': self.seq_separator,
            ',': self.separator,
            '(': '',
            ')': '',
            '[': '',
            ']': '',
            '\'': ''
        }
        result = self.default
        if result:
            for k, v in translate_table.items():
                result = result.replace(k, v)
        return result


VALUES_CLASSES = {
    'Value': EnvVar,
    'BooleanValue': EnvVar,
    'IntegerValue': EnvVar,
    'PositiveIntegerValue': EnvVar,
    'FloatValue': EnvVar,
    'DecimalValue': EnvVar,
    'ListValue': SequenceEnvVar,
    'TupleValue': SequenceEnvVar,
    'SingleNestedListValue': NestedSequenceEnvVar,
    'SingleNestedTupleValue': NestedSequenceEnvVar,
    'BackendsValue': EnvVar,
    'SetValue': EnvVar,
    'DictValue': EnvVar,
    'EmailValue': EnvVar,
    'URLValue': EnvVar,
    'IPValue': EnvVar,
    'RegexValue': RegexEnvVar,
    'PathValue': EnvVar,
    'SecretValue': EnvVar,
    'EmailURLValue': EnvVar,
    'DictBackendMixin': EnvVar,
    'DatabaseURLValue': EnvVar,
    'CacheURLValue': EnvVar,
    'SearchURLValue': EnvVar,
}


def env_variable_factory(cls_name, **kwargs):
    cls = VALUES_CLASSES.get(cls_name)
    return cls(**kwargs, cls_name=cls_name)


class EnvVarFormatter:
    def __init__(self, assignment_lookup_table=None):
        self._assignments = assignment_lookup_table

    @staticmethod
    def _str_node_to_src(node):
        return node.s

    @staticmethod
    def _name_const_node_to_src(node):
        return json.dumps(node.value)

    @staticmethod
    def _num_node_to_src(node):
        return node.n

    def _name_node_to_src(self, node, resolve):

        if resolve:
            return self._try_to_resolve_variable(node.id)
        return node.id

    @staticmethod
    def _generic_node_to_src(node):
        return re.sub(r'\s+', '', astor.to_source(node))

    def _to_source_code(self, node, resolve_variables=False):
        if not issubclass(type(node), ast.AST):
            return node

        nodes_to_src = {
            ast.Name: functools.partial(self._name_node_to_src, resolve=resolve_variables),
            ast.NameConstant: self._name_const_node_to_src,
            ast.Num: self._num_node_to_src,
            ast.Str: self._str_node_to_src,
        }
        node_to_src = nodes_to_src.get(type(node), self._generic_node_to_src)
        return node_to_src(node)

    def _try_to_resolve_variable(self, name_node):
        node = self._assignments.get(name_node)
        if node:
            return self._to_source_code(node)
        else:
            return name_node

    def format_line(self, variable):

        name = self.format_name(variable)

        line = "export {name}=".format(name=name)

        default = self.format_default(variable)
        if default:
            line = "# {line}(Default: {default})".format(line=line, default=default)

        extras = self.format_extras(variable)
        if extras:
            line = "{line}FIXME: {extras}".format(line=line, extras=extras)

        return line

    def format_name(self, variable):
        return "{prefix}_{name}".format(
            prefix=self._to_source_code(variable.environ_prefix, resolve_variables=True),
            name=self._to_source_code(variable.environ_name, resolve_variables=True),
        )

    def format_default(self, variable):
        if variable.default is None:
            return ''
        else:
            return self._to_source_code(variable.default)

    def format_extras(self, variable):
        return ''

