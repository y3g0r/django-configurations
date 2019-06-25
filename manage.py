#!/usr/bin/env python
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings.main')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Test')

if sys.argv[0] and sys.argv[0].endswith('django_test_manage.py'):
    # for PyCharm tests
    print(sys.path)
    import configurations
    configurations.setup()


if __name__ == "__main__":
    from configurations.management import execute_from_command_line

    execute_from_command_line(sys.argv)
