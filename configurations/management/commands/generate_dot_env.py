import ast
import sys

from django.core.management.base import BaseCommand

from configurations.generate_dot_env_utils import CustomisableVariablesFinder


class Command(BaseCommand):
    help = 'Generates .env file template'

    def add_arguments(self, parser):
        parser.add_argument('-i', '--input')
        parser.add_argument('--sort', action='store_true')

    def handle(self, *args, **options):
        settings_file = options['input']
        parsed_settings = self.process(settings_file)
        printable_dump = self.dump(parsed_settings, sort=options['sort'])
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
    def dump_single_variable_specs(variable):
        return str(variable)

    @staticmethod
    def dump(parsed_settings, sort=False):
        finder = CustomisableVariablesFinder(parsed_settings)

        result = []

        variables = finder.variables
        if sort:
            variables.sort(key=lambda v: v.name)

        for variable in variables:
            result.append(Command.dump_single_variable_specs(variable))
            result.append(Command.dump_single_variable(variable))

        return '\n'.join(result)