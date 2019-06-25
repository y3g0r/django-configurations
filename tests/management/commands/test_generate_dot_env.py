import argparse
import ast
import io
import sys
import tempfile
import textwrap
from unittest.mock import patch

import astor
from django.core.management import call_command, CommandError
from django.test import TestCase

from configurations.management.commands.generate_dot_env import Command, ValuesFetcher


class CommandTest(TestCase):
    def setUp(self):
        pass

    @patch('sys.stdin.read', side_effect=['import os'])
    def test__settings_file_provided_in_stdin__file_processed(self, _):
        buf = io.StringIO()
        call_command('generate_dot_env', stdout=buf)
        self.assertIn("Module(body=[Import(names=[alias(name='os', asname=None)])])", buf.getvalue())

    def test__input_parameter_given__using_provided_file(self):
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(b'import os')
            fp.seek(0)

            buf = io.StringIO()
            call_command('generate_dot_env', '--input', fp.name, stdout=buf)

            self.assertIn("Module(body=[Import(names=[alias(name='os', asname=None)])])", buf.getvalue())

    def test_parse__empty_file__results_in_empty_module_tree(self):
        res = Command()._parse('')
        # self.assertEqual(ast.dump(ast.parse('import os')), ast.dump(res))
        self.assertEqual(ast.dump(ast.parse('')), ast.dump(res))

    def test_dump__empty_settings__empty_string_dumped(self):
        module_tree = ast.parse('')
        res = Command().dump(module_tree)
        self.assertEqual('', res)

    def test_dump__unrelated_settings__empty_string(self):
        settings_content = textwrap.dedent("""\
            import os
            def func():
                return 42
            class Settings:
                KEY1 = True
                KEY2 = 'string'
                KEY3 = 1
                KEY4 = [False, 0, '']
            GLOBAL_VARIABLE = object()
            """
        )
        module_tree = ast.parse(settings_content)
        res = Command().dump(module_tree)
        self.assertEqual('', res)

    def test_dump__values_setting__export_env_var_dumped(self):
        settings_content = textwrap.dedent("""\
            class Settings:
                KEY1 = values.Value()
            """
        )
        module_tree = ast.parse(settings_content)
        res = Command().dump(module_tree)
        self.assertEqual('export KEY1=', res)


class ValuesFetcherTest(TestCase):
    def test_1(self):
        """
        Module(
            body=[
                Assign(targets=[Name(id='KEY1')],
                    value=Call(func=Attribute(value=Name(id='values'), attr='Value'), args=[], keywords=[]))])
        """
        tree = ast.parse('KEY1 = values.Value()')
        fetcher = ValuesFetcher()
        fetcher.traverse(tree)
        variables = fetcher.variables
        self.assertEqual('[DJANGO_KEY1]', str(variables))

    def test_2(self):
        """
        Module(
            body=[
                ImportFrom(module='configuration.values', names=[alias(name='Value', asname=None)], level=0),
                Assign(targets=[Name(id='KEY1')], value=Call(func=Name(id='Value'), args=[], keywords=[]))])
        """
        tree = ast.parse('from configuration.values import Value\n'
                         'KEY1 = Value()\n')
        fetcher = ValuesFetcher()
        fetcher.traverse(tree)
        variables = fetcher.variables
        self.assertEqual('[DJANGO_KEY1]', str(variables))

    def test_3(self):
        """
        Module(
            body=[
                Assign(targets=[Name(id='KEY1')],
                    value=Call(func=Attribute(value=Name(id='values'), attr='Value'),
                        args=[],
                        keywords=[keyword(arg='environ_name', value=Str(s='SOMEKEY')),
                            keyword(arg='environ_prefix', value=Str(s='PREFIX'))]))])
        """
        tree = ast.parse('KEY1 = values.Value(environ_name="SOMEKEY", environ_prefix="PREFIX")\n')
        print(astor.dump_tree(tree))

        fetcher = ValuesFetcher()
        fetcher.traverse(tree)
        variables = fetcher.variables
        self.assertEqual('[PREFIX_SOMEKEY]', str(variables))