"""Catalog diagnostics and opt-in gates: no network or hosted PostgreSQL access."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, Mock

import pytest

from backend.commands.postgres_security import security_report


def catalog(*,public_grants=False,api_column=False,rls=True):
    connection = MagicMock()
    table = {'oid':42,'rls_enabled':rls,'rls_forced':False,'owner':True,'bypass_rls':True,
             'resolves_public':True,'schema_usage':True,'schema_create':True,'policy_count':0,'trigger_count':0}
    defaults = [{'creator_oid':99,'global_scope':True,'object_type':'r','public_grant':True,'api_inherited':False,'privilege_type':'SELECT'}] if public_grants else []
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = table
    connection.execute.return_value.mappings.return_value.all.return_value = defaults
    def scalar(statement,params=None):
        sql = str(statement); params=params or {}
        if 'pg_get_serial_sequence' in sql:return 'public.records_id_seq'
        if 'pg_event_trigger' in sql:return 0
        if 'pg_roles WHERE rolname=' in sql:return True
        if 'has_schema_privilege' in sql:return params['role']=='current_user' or params['privilege']=='USAGE'
        if 'has_any_column_privilege' in sql:return params['role']=='current_user' or (api_column and params['role']=='anon' and params['privilege']=='SELECT')
        if 'has_table_privilege' in sql or 'has_sequence_privilege' in sql:return params['role']=='current_user'
        raise AssertionError('Unexpected catalog operation')
    connection.scalar.side_effect=scalar
    return connection


def test_report_checks_effective_privileges_without_customer_queries_or_role_credentials():
    connection=catalog()
    result=security_report(connection)
    assert result['rls_enabled'] and result['current_role_crud_grants'] and not result['review_required']
    assert result['privileges']['current_user']['sequence']['USAGE']
    assert not result['privileges']['anon']['table']['TRUNCATE']
    statements=[str(call.args[0]) for method in (connection.execute,connection.scalar) for call in method.call_args_list]
    assert not any('FROM public.records' in sql or 'records.data' in sql for sql in statements)
    assert all(not sql.lstrip().startswith(('INSERT','UPDATE','DELETE','ALTER','GRANT','REVOKE','TRUNCATE')) for sql in statements)
    assert 'records_id_seq' not in json.dumps(result)


@pytest.mark.parametrize('options',[{'public_grants':True},{'api_column':True},{'rls':False}])
def test_insecure_catalog_state_is_reported_for_review(options):
    report=security_report(catalog(**options))
    assert report['review_required']
    if options.get('public_grants'):
        assert report['future_public_grants']==[{'creator':'creator_1','scope':'global','object':'table','grantee':'PUBLIC','privilege':'SELECT'}]


def test_security_flag_cannot_connect_implicitly(monkeypatch):
    from backend.commands import database_check
    factory=Mock(side_effect=AssertionError('Must not construct an engine'))
    monkeypatch.setattr(database_check,'create_database_engine',factory)
    with pytest.raises(ValueError,match='explicit --connect'):database_check.check(security=True)
    factory.assert_not_called()


def test_hosted_suite_skips_even_if_url_is_present_without_write_opt_in(tmp_path):
    env=dict(os.environ,SWAPSTER_TEST_POSTGRES_URL='postgresql://synthetic:DO_NOT_PRINT@db.example.invalid/postgres?sslmode=require')
    env.pop('SWAPSTER_PG_INTEGRATION',None);env.pop('SWAPSTER_PG_WRITE_ACK',None)
    code='''
from unittest.mock import patch
import pytest
with patch('psycopg.connect',side_effect=AssertionError('Hosted connection forbidden')):
    raise SystemExit(pytest.main(['backend/integration_tests','backend/tests/test_database.py::test_sqlite_is_default_only_when_database_url_is_unset','-q','-p','no:cacheprovider']))
'''
    result=subprocess.run([sys.executable,'-c',code],env=env,cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True)
    assert result.returncode==0 and '1 passed, 5 skipped' in result.stdout
    assert 'DO_NOT_PRINT' not in result.stdout+result.stderr


def test_cleanup_runs_after_assertion_failure_and_deletes_only_exact_synthetic_namespace():
    from backend.integration_tests.conftest import isolated
    engine=MagicMock()
    connection=engine.begin.return_value.__enter__.return_value
    connection.scalar.return_value=None
    request=MagicMock()
    fixture=isolated.__wrapped__(engine,request)
    _,namespace=next(fixture)
    assert namespace.startswith('integration_4d_')
    with pytest.raises(pytest.fail.Exception):fixture.throw(AssertionError('synthetic failure'))
    statement=connection.execute.call_args.args[0]
    sql=str(statement.compile())
    assert sql.startswith('DELETE FROM records WHERE records.kind =')
    assert list(statement.compile().params.values())==[namespace]
    connection.scalar.assert_called_once()


def test_hosted_failure_report_suppresses_credentials_and_logs():
    from backend.integration_tests.conftest import pytest_runtest_makereport
    item=MagicMock()
    item.path=Path(__file__).resolve().parents[1]/'integration_tests/test_postgresql.py'
    item._pg_namespace='integration_4d_synthetic'
    report=MagicMock(failed=True,longrepr='DO_NOT_PRINT')
    report.sections=[('stderr','DO_NOT_PRINT')]
    outcome=MagicMock()
    outcome.get_result.return_value=report
    hook=pytest_runtest_makereport(item,None)
    next(hook)
    with pytest.raises(StopIteration):hook.send(outcome)
    assert 'DO_NOT_PRINT' not in report.longrepr
    assert 'integration_4d_synthetic' in report.longrepr
    assert report.sections==[]
