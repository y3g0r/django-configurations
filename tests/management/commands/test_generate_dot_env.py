import ast
import io
import tempfile
import textwrap
from unittest import skip
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from configurations.management.commands.generate_dot_env import Command, CustomisableVariablesFinder
from configurations.generate_dot_env_utils import ValuesVisitor

t = textwrap.dedent


class CommandTest(TestCase):
    maxDiff = None

    @patch('sys.stdin.read', side_effect=['SECRET_KEY = values.SecretValue()'])
    def test__settings_file_provided_in_stdin__file_processed(self, _):
        buf = io.StringIO()
        call_command('generate_dot_env', stdout=buf)
        self.assertEqual(
            "# DJANGO_SECRET_KEY: Secret\n"
            "export DJANGO_SECRET_KEY=\n",
            buf.getvalue()
        )

    def test__input_parameter_given__using_provided_file(self):
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(b'SECRET_KEY = values.SecretValue()')
            fp.seek(0)

            buf = io.StringIO()
            call_command('generate_dot_env', '--input', fp.name, stdout=buf)

            self.assertEqual(
                "# DJANGO_SECRET_KEY: Secret\n"
                "export DJANGO_SECRET_KEY=\n",
                buf.getvalue()
            )

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

    def out(self, code):
        with patch('sys.stdin.read', side_effect=[code]):
            buf = io.StringIO()
            call_command('generate_dot_env', stdout=buf)
            return buf.getvalue()

    def test_1(self):
        self.assertEqual(
            t("""\
            # DJANGO_DEBUG: Boolean=True
            export DJANGO_DEBUG=
            """),
            self.out(t("""\
                from configurations import Configuration, values
        
                class Dev(Configuration):
                    DEBUG = values.BooleanValue(True)
                """
            ))
        )

    def test_2(self):
        self.assertEqual(
            t("""\
            # DJANGO_DEBUG: Boolean=True
            export DJANGO_DEBUG=
            # DJANGO_TEMPLATE_DEBUG: Boolean=Variable: DEBUG = values.BooleanValue(True)
            export DJANGO_TEMPLATE_DEBUG=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Dev(Configuration):
                    DEBUG = values.BooleanValue(True)
                    TEMPLATE_DEBUG = values.BooleanValue(DEBUG)
                """
            ))
        )

    def test_3(self):
        self.assertEqual(
            t("""\
            # DJANGO_ROOT_URLCONF: String=mysite.urls
            export DJANGO_ROOT_URLCONF=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Stage(Configuration):
                    # ..
                    ROOT_URLCONF = values.Value('mysite.urls')
                """
            ))
        )

    def test_4(self):
        self.assertEqual(
            "\n",
            self.out(t("""\
                from configurations import Configuration, values
                
                class Dev(Configuration):
                    TIME_ZONE = values.Value('UTC', environ=False)
                """
            ))
        )

    def test_5(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_TZ: String=UTC
            export DJANGO_MYSITE_TZ=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Dev(Configuration):
                    TIME_ZONE = values.Value('UTC', environ_name='MYSITE_TZ')
                """
            ))
        )

    def test_6(self):
        self.assertEqual(
            t("""\
            # MYSITE_TIME_ZONE: String=UTC
            export MYSITE_TIME_ZONE=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Dev(Configuration):
                    TIME_ZONE = values.Value('UTC', environ_prefix='MYSITE')
                """
            ))
        )

    def test_7(self):
        self.assertEqual(
            t("""\
            # DJANGO_TIME_ZONE: String
            export DJANGO_TIME_ZONE=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Dev(Configuration):
                    TIME_ZONE = values.Value()
                """
            ))
        )

    def test_8(self):
        self.assertEqual(
            t("""\
            # DJANGO_DEBUG: Boolean=True
            export DJANGO_DEBUG=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    DEBUG = values.BooleanValue(True)
                """
            ))
        )

    def test_9(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_CACHE_TIMEOUT: Integer=3600
            export DJANGO_MYSITE_CACHE_TIMEOUT=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_CACHE_TIMEOUT = values.IntegerValue(3600)
                """
            ))
        )

    def test_10(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_CACHE_TIMEOUT: Integer=(60 * 60)
            export DJANGO_MYSITE_CACHE_TIMEOUT=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_CACHE_TIMEOUT = values.IntegerValue(60 * 60)
                """
            ))
        )

    def test_11(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_CACHE_TIMEOUT: Integer=cache_timeout()
            export DJANGO_MYSITE_CACHE_TIMEOUT=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_CACHE_TIMEOUT = values.IntegerValue(cache_timeout())
                """
            ))
        )

    def test_12(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_WORKER_POOL: PositiveInteger=8
            export DJANGO_MYSITE_WORKER_POOL=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_WORKER_POOL = values.PositiveIntegerValue(8)
                """
            ))
        )

    def test_13(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_TAX_RATE: Float=11.9
            export DJANGO_MYSITE_TAX_RATE=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_TAX_RATE = values.FloatValue(11.9)
                """
            ))
        )

    def test_14(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_CONVERSION_RATE: Decimal=decimal.Decimal('4.56214')
            export DJANGO_MYSITE_CONVERSION_RATE=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_CONVERSION_RATE = values.DecimalValue(decimal.Decimal('4.56214'))
                """
            ))
        )

    def test_15(self):
        self.assertEqual(
            t("""\
            # DJANGO_MYSITE_CONVERSION_RATE: Decimal=1
            export DJANGO_MYSITE_CONVERSION_RATE=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MYSITE_CONVERSION_RATE = values.DecimalValue(1)
                """
            ))
        )

    def test_list_value_default_list(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: List=mysite.com,mysite.biz (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.ListValue(['mysite.com', 'mysite.biz'])
                """
            ))
        )

    def test_list_value_default_tuple(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: List=mysite.com,mysite.biz (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.ListValue(('mysite.com', 'mysite.biz'))
                """
            ))
        )

    def test_list_value_default_nothing(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: List (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.ListValue()
                """
            ))
        )

    def test_list_value_default_empty_list(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: List=[] (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.ListValue([])
                """
            ))
        )

    def test_list_value_default_list_constructor(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: List=list() (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.ListValue(list())
                """
            ))
        )

    def test_list_value_default_list_custom_separator(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: List=mysite.com:mysite.biz (separator=:)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.ListValue(['mysite.com', 'mysite.biz'], separator=':')
                """
            ))
        )

    def test_tuple_value_default_nothing(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: Tuple (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.TupleValue()
                """
            ))
        )

    def test_tuple_value_default_tuple(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: Tuple=mysite.com,mysite.biz (separator=,)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.TupleValue(('mysite.com', "mysite.biz",))
                """
            ))
        )

    def test_tuple_value_default_list_custom_separator(self):
        self.assertEqual(
            t("""\
            # DJANGO_ALLOWED_HOSTS: Tuple=mysite.com/mysite.biz (separator=/)
            export DJANGO_ALLOWED_HOSTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ALLOWED_HOSTS = values.TupleValue(['mysite.com', "mysite.biz",], separator='/')
                """
            ))
        )

    def test_singe_nested_tuple_value_default_nothing(self):
        self.assertEqual(
            t("""\
            # DJANGO_ADMINS: SingleNestedTuple (separator=,) (seq_separator=;)
            export DJANGO_ADMINS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ADMINS = values.SingleNestedTupleValue()
                """
            ))
        )

    def test_singe_nested_tuple_value_default_nested_tuple(self):
        self.assertEqual(
            t("""\
            # DJANGO_ADMINS: SingleNestedTuple=John,jcleese@site.com;Eric,eidle@site.com (separator=,) (seq_separator=;)
            export DJANGO_ADMINS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ADMINS = values.SingleNestedTupleValue((
                        ('John', 'jcleese@site.com'),
                        ('Eric', 'eidle@site.com'),
                    ))
                """
            ))
        )

    def test_singe_nested_list_value_default_nothing(self):
        self.assertEqual(
            t("""\
            # DJANGO_ADMINS: SingleNestedList (separator=,) (seq_separator=;)
            export DJANGO_ADMINS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ADMINS = values.SingleNestedListValue()
                """
            ))
        )

    def test_singe_nested_list_value_default_nested_list(self):
        self.assertEqual(
            t("""\
            # DJANGO_ADMINS: SingleNestedList=John,jcleese@site.com;Eric,eidle@site.com (separator=,) (seq_separator=;)
            export DJANGO_ADMINS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ADMINS = values.SingleNestedListValue([
                        ['John', 'jcleese@site.com'],
                        ['Eric', 'eidle@site.com'],
                    ])
                """
            ))
        )

    def test_singe_nested_list_value_custom_separators(self):
        self.assertEqual(
            t("""\
            # DJANGO_ADMINS: SingleNestedList=John|jcleese@site.com}{Eric|eidle@site.com (separator=|) (seq_separator=}{)
            export DJANGO_ADMINS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    ADMINS = values.SingleNestedListValue([
                        ['John', 'jcleese@site.com'],
                        ['Eric', 'eidle@site.com'],
                    ], separator='|', seq_separator='}{')
                """
            ))
        )

    def test_set_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_NUMBERS: Set=one,two,tree (separator=,)
            export DJANGO_NUMBERS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    NUMBERS = values.SetValue(['one', 'two', 'tree'])
                """
            ))
        )

    def test_set_value_one_default(self):
        self.assertEqual(
            t("""\
            # DJANGO_NUMBERS: Set=one (separator=,)
            export DJANGO_NUMBERS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    NUMBERS = values.SetValue({'one'})
                """
            ))
        )

    def test_dict_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_DEPARTMENTS: Dict={'it': ['Mike', 'Joe']}
            export DJANGO_DEPARTMENTS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    DEPARTMENTS = values.DictValue({
                        'it': ['Mike', 'Joe'],
                    })
                """
            ))
        )

    def test_email_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_SUPPORT_EMAIL: Email=support@mysite.com
            export DJANGO_SUPPORT_EMAIL=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    SUPPORT_EMAIL = values.EmailValue('support@mysite.com')
                """
            ))
        )

    def test_url_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_SUPPORT_URL: URL=https://support.mysite.com/
            export DJANGO_SUPPORT_URL=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    SUPPORT_URL = values.URLValue('https://support.mysite.com/')
                """
            ))
        )

    def test_ip_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_LOADBALANCER_IP: IP=127.0.0.1
            export DJANGO_LOADBALANCER_IP=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    LOADBALANCER_IP = values.IPValue('127.0.0.1')
                """
            ))
        )

    def test_regex_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_DEFAULT_SKU: Regex=000-000-00 (regex=\d{3}-\d{3}-\d{2})
            export DJANGO_DEFAULT_SKU=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    DEFAULT_SKU = values.RegexValue('000-000-00', regex=r'\d{3}-\d{3}-\d{2}')
                """
            ))
        )

    def test_path_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_BASE_DIR: Path=/opt/mysite/ (checks_exists=True)
            export DJANGO_BASE_DIR=
            # DJANGO_STATIC_ROOT: Path=/var/www/static (checks_exists=False)
            export DJANGO_STATIC_ROOT=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    BASE_DIR = values.PathValue('/opt/mysite/')
                    STATIC_ROOT = values.PathValue('/var/www/static', checks_exists=False)
                """
            ))
        )

    def test_database_url_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_DATABASES: DatabaseURL=postgres://myuser@localhost/mydb
            export DJANGO_DATABASES=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    DATABASES = values.DatabaseURLValue('postgres://myuser@localhost/mydb')
                """
            ))
        )

    def test_cache_url_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_CACHES: CacheURL=memcached://127.0.0.1:11211/
            export DJANGO_CACHES=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    CACHES = values.CacheURLValue('memcached://127.0.0.1:11211/')
                """
            ))
        )

    def test_email_url_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_EMAIL: EmailURL=console://
            export DJANGO_EMAIL=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    EMAIL = values.EmailURLValue('console://')
                """
            ))
        )

    def test_search_url_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_HAYSTACK_CONNECTIONS: SearchURL=elasticsearch://127.0.0.1:9200/my-index
            export DJANGO_HAYSTACK_CONNECTIONS=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    HAYSTACK_CONNECTIONS = values.SearchURLValue('elasticsearch://127.0.0.1:9200/my-index')
                """
            ))
        )

    def test_backends_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_MIDDLEWARE_CLASSES: Backends=django.middleware.common.CommonMiddleware,django.contrib.sessions.middleware.SessionMiddleware,django.middleware.csrf.CsrfViewMiddleware,django.contrib.auth.middleware.AuthenticationMiddleware,django.contrib.messages.middleware.MessageMiddleware,django.middleware.clickjacking.XFrameOptionsMiddleware (separator=,)
            export DJANGO_MIDDLEWARE_CLASSES=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    MIDDLEWARE_CLASSES = values.BackendsValue([
                        'django.middleware.common.CommonMiddleware',
                        'django.contrib.sessions.middleware.SessionMiddleware',
                        'django.middleware.csrf.CsrfViewMiddleware',
                        'django.contrib.auth.middleware.AuthenticationMiddleware',
                        'django.contrib.messages.middleware.MessageMiddleware',
                        'django.middleware.clickjacking.XFrameOptionsMiddleware',
                    ])
                """
            ))
        )

    def test_secret_value(self):
        self.assertEqual(
            t("""\
            # DJANGO_SECRET_KEY: Secret
            export DJANGO_SECRET_KEY=
            """),
            self.out(t("""\
                from configurations import Configuration, values
                
                class Settings(Configuration):
                    SECRET_KEY = values.SecretValue()
                """
            ))
        )

