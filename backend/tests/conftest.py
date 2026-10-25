import os, tempfile
from pathlib import Path
_test_dir=tempfile.TemporaryDirectory(prefix='campusswap-tests-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_test_dir.name)/'test.db')
os.environ['ENABLE_JUDGE_MODE']='false'
os.environ['APP_ENV']='development'
