import os, tempfile
from pathlib import Path
_test_dir=tempfile.TemporaryDirectory(prefix='campusswap-tests-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_test_dir.name)/'test.db')
os.environ['ENABLE_JUDGE_MODE']='false'
os.environ['APP_ENV']='development'
# Tests never inherit live Auth credentials or depend on a configured Supabase project.
# Auth tests explicitly install synthetic settings and mocked network responses.
os.environ['SUPABASE_URL']=''
os.environ['SUPABASE_PUBLISHABLE_KEY']=''
os.environ['SUPABASE_AUTH_LEGACY_HS256']='false'
