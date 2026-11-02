"""Explicitly authorized PostgreSQL writes only. No application startup or migrations."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
from queue import Queue
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, text

from backend.models.records import Record
from backend.commands.postgres_security import security_report
from .conftest import scoped_session


def synthetic(actor):
    return {'version':0,'buyer_id':actor,'seller_id':str(uuid4()),'listing_id':0,
            'listing_version':0,'item':{},'preferences':{},'created_at':'2030-01-01T00:00:00+00:00',
            'approvals':{},'status':'integration-test'}


def create(engine, namespace, data):
    with scoped_session(engine) as db:
        record = Record(kind=namespace,data=data)
        db.add(record)
        db.flush()
        id = record.id
        db.commit()
        return id


def own(db, namespace, id):
    return db.scalar(select(Record).where(Record.kind==namespace,Record.id==id))


def test_committed_crud_persists_across_independent_sessions_and_connections(isolated):
    engine, namespace = isolated
    actor = str(uuid4())
    id = create(engine,namespace,synthetic(actor))  # Verifies actual INSERT + sequence access.
    with scoped_session(engine) as first, scoped_session(engine) as second:
        assert first.scalar(text('SELECT pg_backend_pid()')) != second.scalar(text('SELECT pg_backend_pid()'))
        assert own(first,namespace,id).data['version'] == 0
        record = own(second,namespace,id)
        record.data = dict(record.data,version=1)
        second.commit()
        first.expire_all()
        assert own(first,namespace,id).data['version'] == 1
    with scoped_session(engine) as db:
        assert db.execute(delete(Record).where(Record.kind==namespace,Record.id==id)).rowcount == 1
        db.commit()
    with scoped_session(engine) as db:
        assert own(db,namespace,id) is None


def test_rollback_never_persists_synthetic_update(isolated):
    engine, namespace = isolated
    id = create(engine,namespace,synthetic(str(uuid4())))
    with scoped_session(engine) as db:
        record=own(db,namespace,id)
        record.data=dict(record.data,version=99)
        db.flush()
        db.rollback()
    with scoped_session(engine) as db:
        assert own(db,namespace,id).data['version']==0


def test_actual_application_cas_allows_one_winner_for_same_version(isolated):
    from backend.services.account_marketplace import compare_and_swap
    engine, namespace = isolated
    actor=str(uuid4())
    id=create(engine,namespace,synthetic(actor))
    barrier=Barrier(2)
    def writer():
        with scoped_session(engine) as db:
            previous=dict(deepcopy(own(db,namespace,id).data),id=id)
            changed=deepcopy(previous)
            changed['status']='updated-by-test'
            barrier.wait(timeout=10)
            try:
                compare_and_swap(db,namespace,previous,changed,actor)
                db.commit()
                return 'committed'
            except HTTPException as error:
                db.rollback()
                assert error.status_code==409
                return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:writer(),range(2)))
    assert sorted(results)==['committed','conflict']
    with scoped_session(engine) as db:
        assert own(db,namespace,id).data['version']==1


def test_row_lock_waits_then_read_committed_observes_new_version(isolated):
    from backend.services.account_marketplace import row
    engine, namespace = isolated
    id=create(engine,namespace,synthetic(str(uuid4())))
    attempted,acquired=Event(),Event()
    waiter_pid=Queue(maxsize=1)
    def waiter():
        with scoped_session(engine) as db:
            waiter_pid.put(db.scalar(text('SELECT pg_backend_pid()')))
            attempted.set()
            result=row(db,namespace,id,lock=True)
            acquired.set()
            return result['version']
    with ThreadPoolExecutor(max_workers=1) as pool:
        with scoped_session(engine) as owner:
            record=owner.scalar(select(Record).where(Record.kind==namespace,Record.id==id).with_for_update())
            future=pool.submit(waiter)
            assert attempted.wait(5)
            pid=waiter_pid.get(timeout=5)
            deadline=time.monotonic()+2
            blocked=False
            while time.monotonic()<deadline:
                blocked=bool(owner.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:pid AND NOT granted)'),{'pid':pid}))
                if blocked:break
                time.sleep(.05)
            assert blocked and not acquired.is_set()
            record.data=dict(record.data,version=1)
            owner.commit()
        assert future.result(timeout=10)==1


def test_default_grants_and_role_security_review(isolated):
    engine, _ = isolated
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
        report=security_report(connection)
        assert report['rls_enabled'] and report['current_role_crud_grants']
        assert not report['future_public_grants']
        assert not report['review_required']
