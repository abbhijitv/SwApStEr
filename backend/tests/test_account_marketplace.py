"""Real verified multi-user requests and independent database writers; no live Auth."""
import copy
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql, sqlite

from backend import auth
from backend.main import app
from backend.models.database import Record, Session
from backend.services import account_marketplace as service
from backend.services.store import get, save
from backend.agents.mock_provider import MockProvider

ROOT = Path(__file__).resolve().parents[2]
USERS = ['97e67eaa-7313-47cd-aae8-1294dd91a6f9', '307b690e-e958-4b7e-9444-2588b5fe2b36', '8d185b0b-29bc-4b3b-b1fd-c53989982a3a']
PROJECT = 'https://marketplace-auth.example.invalid'


@pytest.fixture(scope='module')
def signing():
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    public.update(kid='marketplace-test-key', alg='ES256', use='sig')
    return private, {'keys': [public]}


@pytest.fixture(autouse=True)
def settings(monkeypatch, signing):
    monkeypatch.setenv('ENABLE_ACCOUNT_MARKETPLACE', 'true')
    monkeypatch.setenv('SUPABASE_URL', PROJECT)
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_synthetic-marketplace')
    auth.jwks_client.cache_clear()
    opener = Mock()
    opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(signing[1]).encode())
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: opener)
    yield
    auth.jwks_client.cache_clear()


@pytest.fixture
def clients(signing):
    clients = []
    for identity in USERS:
        issued = int(time.time())
        token = jwt.encode({'iss': PROJECT+'/auth/v1', 'aud': 'authenticated', 'sub': identity,
                            'iat': issued-1, 'exp': issued+3600, 'role': 'authenticated'}, signing[0], algorithm='ES256', headers={'kid': 'marketplace-test-key'})
        clients.append(TestClient(app, headers={'Authorization': 'Bearer '+token}))
    yield clients
    for client in clients:
        client.close()


def listing_body(**changes):
    start = datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=3)
    return {'title': 'Account marketplace test item', 'description': 'A maintained item with all accessories.',
            'category': 'Electronics', 'price': '35', 'minimum': '19.87', 'type': 'Rent', 'rental_days': 3,
            'windows': [{'start': start.isoformat(), 'end': (start+timedelta(hours=4)).isoformat()}],
            'available_until': (start+timedelta(days=10)).isoformat(), **changes}


def create(client, **changes):
    response = client.post('/marketplace/listings', json=listing_body(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def preferences(listing, **changes):
    return {'listing_id': listing['id'], 'target': '15', 'maximum': '27.13', 'rental_days': 3,
            'windows': listing['windows'], 'deadline': listing['available_until'], 'location': 'Public library entrance', 'provider': 'mock', **changes}


def start(buyer, listing, **changes):
    response = buyer.post('/marketplace/negotiations', json=preferences(listing, **changes))
    assert response.status_code == 201, response.text
    return response.json()


def pending(buyer, seller):
    listing = create(seller)
    negotiation = start(buyer, listing)
    for _ in range(10):
        if negotiation['status'] not in ('Negotiating', 'Agreement proposed'):
            break
        response = buyer.post(f"/marketplace/negotiations/{negotiation['id']}/advance", json={'version': negotiation['version']})
        assert response.status_code == 200, response.text
        negotiation = response.json()
    assert negotiation['status'] == 'Awaiting approvals', negotiation
    assert not any(negotiation['approvals'].values())
    return listing, negotiation


def stored(kind, id):
    with Session() as db:
        record = db.scalar(select(Record).where(Record.kind == kind, Record.id == id))
        assert record is not None
        return dict(copy.deepcopy(record.data), id=record.id)


def assert_no_constraints(value):
    if isinstance(value, dict):
        assert not {'minimum', 'maximum', 'preferences', 'audit_events', 'private', 'email', 'user_metadata'} & set(value)
        for child in value.values(): assert_no_constraints(child)
    elif isinstance(value, list):
        for child in value: assert_no_constraints(child)


def test_staged_api_is_off_by_default(monkeypatch, clients):
    monkeypatch.delenv('ENABLE_ACCOUNT_MARKETPLACE')
    assert clients[0].get('/marketplace/listings').status_code == 404
    assert clients[0].post('/marketplace/listings', json=listing_body()).status_code == 404


def test_listing_ownership_public_projection_and_management(clients):
    a, b, c = clients
    listing = create(b)
    assert listing['seller_id'] == USERS[1] and listing['minimum'] == '19.87'
    before = stored(service.LISTING, listing['id'])
    body = dict(listing_body(title='Forbidden edit'), version=listing['version'])
    assert a.put(f"/marketplace/listings/{listing['id']}", json=body).status_code == 403
    assert a.delete(f"/marketplace/listings/{listing['id']}?version=0").status_code == 403
    assert a.get(f"/marketplace/listings/{listing['id']}/manage").status_code == 403
    assert stored(service.LISTING, listing['id']) == before
    with TestClient(app) as anonymous:
        public = anonymous.get(f"/marketplace/listings/{listing['id']}")
        assert public.status_code == 200
        assert_no_constraints(public.json())
        assert 'seller_id' not in public.json() and USERS[1] not in public.text
    changed = b.put(f"/marketplace/listings/{listing['id']}", json=body)
    assert changed.status_code == 200 and changed.json()['version'] == 1
    assert b.put(f"/marketplace/listings/{listing['id']}", json=body).status_code == 409
    assert b.get('/marketplace/listings/mine').json()[-1]['id'] == listing['id']
    assert listing['id'] not in [item['id'] for item in c.get('/marketplace/listings/mine').json()]
    assert b.delete(f"/marketplace/listings/{listing['id']}?version=1").status_code == 204
    assert b.get(f"/marketplace/listings/{listing['id']}").status_code == 404
    assert b.get(f"/marketplace/listings/{listing['id']}/manage").json()['deleted'] is True
    assert stored(service.LISTING, listing['id'])['minimum'] == '19.87'


@pytest.mark.parametrize('field', ['id', 'seller_id', 'buyer_id', 'owner_id', 'version', 'deleted', 'approvals'])
def test_listing_browser_cannot_assign_identity_or_state(clients, field):
    assert clients[0].post('/marketplace/listings', json=listing_body(**{field: USERS[1]})).status_code == 422


@pytest.mark.parametrize('field', ['buyer_id', 'seller_id', 'role', 'approvals', 'status', 'agreement', 'version'])
def test_negotiation_browser_cannot_assign_identity_or_state(clients, field):
    listing = create(clients[1])
    assert clients[0].post('/marketplace/negotiations', json=preferences(listing, **{field: USERS[1]})).status_code == 422


def test_negotiation_uses_verified_participants_and_rejects_self_dealing(clients):
    a, b, c = clients
    listing = create(b)
    assert b.post('/marketplace/negotiations', json=preferences(listing)).status_code == 403
    negotiation = start(a, listing)
    assert negotiation['buyer_id'] == USERS[0] and negotiation['seller_id'] == USERS[1]
    assert set(negotiation['approvals']) == {USERS[0], USERS[1]}
    assert_no_constraints(negotiation)
    id = negotiation['id']
    before = stored(service.NEGOTIATION, id)
    for suffix, payload in [('/advance', {'version': 0}), ('/approve', {'version': 0, 'decision': 'approve'}), ('/cancel', {'version': 0})]:
        assert c.post(f'/marketplace/negotiations/{id}'+suffix, json=payload).status_code == 404
    assert c.get(f'/marketplace/negotiations/{id}').status_code == 404
    assert id not in [n['id'] for n in c.get('/marketplace/negotiations').json()]
    assert stored(service.NEGOTIATION, id) == before
    assert id in [n['id'] for n in b.get('/marketplace/negotiations').json()]


def test_independent_human_approvals_and_replay_protection(clients):
    a, b, c = clients
    listing, proposal = pending(a, b)
    id = proposal['id']
    assert c.post(f'/marketplace/negotiations/{id}/approve', json={'version': proposal['version'], 'decision': 'approve'}).status_code == 404
    for forged in ({'role': 'seller'}, {'seller_id': USERS[1]}, {'student': USERS[1]}, {'approvals': {USERS[1]: True}}):
        assert a.post(f'/marketplace/negotiations/{id}/approve', json={'version': proposal['version'], 'decision': 'approve', **forged}).status_code == 422
    first = a.post(f'/marketplace/negotiations/{id}/approve', json={'version': proposal['version'], 'decision': 'approve'})
    assert first.status_code == 200
    item = first.json()
    assert item['status'] == 'Awaiting approvals' and item['approvals'] == {USERS[0]: True, USERS[1]: False}
    assert a.post(f'/marketplace/negotiations/{id}/approve', json={'version': item['version'], 'decision': 'approve'}).status_code == 409
    assert b.post(f'/marketplace/negotiations/{id}/approve', json={'version': proposal['version'], 'decision': 'approve'}).status_code == 409
    final = b.post(f'/marketplace/negotiations/{id}/approve', json={'version': item['version'], 'decision': 'approve'})
    assert final.status_code == 200 and final.json()['status'] == 'Confirmed'
    assert all(final.json()['approvals'].values())
    assert b.post(f'/marketplace/negotiations/{id}/approve', json={'version': final.json()['version'], 'decision': 'reject'}).status_code == 409
    events = stored(service.NEGOTIATION, id)['audit_events']
    assert sum(e['category'] == 'agreement_finalized' for e in events) == 1
    assert_no_constraints(final.json())


def test_seller_cannot_approve_as_buyer_and_rejection_is_terminal(clients):
    a, b, _ = clients
    _, proposal = pending(a, b)
    path = f"/marketplace/negotiations/{proposal['id']}/approve"
    assert b.post(path, json={'version': proposal['version'], 'decision': 'approve', 'role': 'buyer'}).status_code == 422
    first = b.post(path, json={'version': proposal['version'], 'decision': 'approve'}).json()
    assert first['approvals'] == {USERS[0]: False, USERS[1]: True}
    rejected = a.post(path, json={'version': first['version'], 'decision': 'reject'})
    assert rejected.status_code == 200 and rejected.json()['status'] == 'Rejected'
    assert b.post(path, json={'version': rejected.json()['version'], 'decision': 'approve'}).status_code == 409


def test_agent_contexts_and_participant_responses_keep_private_limits_separate(clients, monkeypatch):
    captured = []
    original = MockProvider.decide
    def spy(self, context):
        captured.append(copy.deepcopy(context))
        return original(self, context)
    monkeypatch.setattr(MockProvider, 'decide', spy)
    listing, proposal = pending(clients[0], clients[1])
    for context in captured:
        text = json.dumps(context)
        if context['role'] == 'buyer': assert 'minimum' not in text and '19.87' not in text
        else: assert 'maximum' not in text and '27.13' not in text
        assert context['principal']['id'] == USERS[0 if context['role'] == 'buyer' else 1]
    for client in clients[:2]:
        response = client.get(f"/marketplace/negotiations/{proposal['id']}")
        assert_no_constraints(response.json())
        assert '19.87' not in response.text and '27.13' not in response.text
        assert_no_constraints(client.get('/marketplace/negotiations').json())
    internal = stored(service.NEGOTIATION, proposal['id'])
    assert internal['preferences']['maximum'] == '27.13'
    assert stored(service.LISTING, listing['id'])['minimum'] == '19.87'


def test_demo_routes_cannot_read_or_mutate_real_records_and_real_routes_reject_demo_cookie(clients, monkeypatch):
    listing, proposal = pending(clients[0], clients[1])
    before = stored(service.NEGOTIATION, proposal['id'])
    with TestClient(app) as demo:
        assert demo.post('/demo/session', json={'student': 'student-a'}).status_code == 200
        assert demo.get(f"/listings/{listing['id']}").status_code == 404
        assert demo.get(f"/negotiations/{proposal['id']}").status_code == 404
        monkeypatch.setenv('ENABLE_JUDGE_MODE', 'true')
        assert demo.get(f"/demo/judge/{proposal['id']}").status_code == 404
        assert demo.post(f"/negotiations/{proposal['id']}/approve", json={'decision': 'approve'}).status_code == 404
        assert demo.post('/negotiations', json=preferences(listing)).status_code == 404
        for path in ('/marketplace/listings/mine', f"/marketplace/listings/{listing['id']}/manage", '/marketplace/negotiations', f"/marketplace/negotiations/{proposal['id']}"):
            assert demo.get(path).status_code == 401
        assert demo.post('/marketplace/listings', json=listing_body()).status_code == 401
        assert demo.post(f"/marketplace/negotiations/{proposal['id']}/approve", json={'decision': 'approve', 'version': proposal['version']}).status_code == 401
        assert not any(profile['id'] in USERS for profile in demo.get('/students').json())
    assert stored(service.NEGOTIATION, proposal['id']) == before
    assert get('listing', listing['id']) is None and get('negotiation', proposal['id']) is None
    with pytest.raises(ValueError): save('negotiation', {'status': 'forged'}, proposal['id'])
    assert stored(service.NEGOTIATION, proposal['id']) == before


def test_invalid_expired_and_forged_identity_tokens_are_rejected(clients, signing):
    with TestClient(app) as client:
        for subject, exp in [(USERS[0], int(time.time())-10), ('student-a', int(time.time())+100)]:
            token = jwt.encode({'iss': PROJECT+'/auth/v1', 'aud': 'authenticated', 'sub': subject, 'iat': int(time.time())-20, 'exp': exp, 'role': 'authenticated'}, signing[0], algorithm='ES256', headers={'kid': 'marketplace-test-key'})
            assert client.post('/marketplace/listings', json=listing_body(), headers={'Authorization': 'Bearer '+token}).status_code == 401
        forged = jwt.encode({'iss': PROJECT+'/auth/v1', 'aud': 'authenticated', 'sub': USERS[1], 'iat': int(time.time())-1, 'exp': int(time.time())+100, 'role': 'authenticated'}, ec.generate_private_key(ec.SECP256R1()), algorithm='ES256', headers={'kid': 'marketplace-test-key'})
        assert client.post('/marketplace/listings', json=listing_body(), headers={'Authorization': 'Bearer '+forged}).status_code == 401
        assert client.post('/marketplace/listings', json=listing_body(), headers={'X-User-ID': USERS[1]}).status_code == 401


def test_listing_freeze_cancellation_and_soft_delete(clients):
    listing = create(clients[1])
    negotiation = start(clients[0], listing)
    assert clients[1].put(f"/marketplace/listings/{listing['id']}", json=dict(listing_body(), version=0)).status_code == 409
    closed = clients[1].post(f"/marketplace/negotiations/{negotiation['id']}/cancel", json={'version': 0})
    assert closed.status_code == 200 and closed.json()['status'] == 'Cancelled'
    assert clients[0].post(f"/marketplace/negotiations/{negotiation['id']}/advance", json={'version': 1}).status_code == 409
    assert clients[1].delete(f"/marketplace/listings/{listing['id']}?version=0").status_code == 204
    assert clients[0].get(f"/marketplace/negotiations/{negotiation['id']}").json()['status'] == 'Cancelled'


def test_owner_withdrawal_cancels_unfinished_negotiations_atomically(clients):
    listing = create(clients[1])
    first = start(clients[0], listing)
    second = start(clients[2], listing)
    assert clients[0].delete(f"/marketplace/listings/{listing['id']}?version=0").status_code == 403
    assert clients[1].delete(f"/marketplace/listings/{listing['id']}?version=0").status_code == 204
    for client, item in ((clients[0], first), (clients[2], second)):
        result = client.get(f"/marketplace/negotiations/{item['id']}")
        assert result.json()['status'] == 'Cancelled' and result.json()['version'] == 1
        assert stored(service.NEGOTIATION, item['id'])['preferences']['maximum'] == '27.13'
    assert clients[0].get(f"/marketplace/listings/{listing['id']}").status_code == 404


def test_withdrawal_and_last_approval_are_serialized_on_the_listing(clients):
    listing, item = pending(clients[0], clients[1])
    first = clients[0].post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': item['version'], 'decision': 'approve'}).json()
    def operation(index):
        if index == 0:
            with TestClient(app, headers=dict(clients[1].headers)) as client:
                return client.post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': first['version'], 'decision': 'approve'})
        return clients[1].delete(f"/marketplace/listings/{listing['id']}?version=0")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, [0, 1]))
    assert results[1].status_code == 204
    assert results[0].status_code in (200, 404, 409)
    latest = stored(service.NEGOTIATION, item['id'])
    assert latest['status'] in {'Confirmed', 'Cancelled'}
    assert all(latest['approvals'].values()) == (latest['status'] == 'Confirmed')
    assert stored(service.LISTING, listing['id'])['deleted'] is True


def test_browser_cannot_submit_raw_offer_or_agent_approval_state(clients):
    listing = create(clients[1])
    item = start(clients[0], listing)
    path = f"/marketplace/negotiations/{item['id']}/advance"
    for extra in ({'role': 'seller'}, {'terms': {'price': '1'}}, {'approvals': {USERS[1]: True}}, {'action': 'ACCEPT'}):
        assert clients[0].post(path, json={'version': 0, **extra}).status_code == 422
    assert clients[0].post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': 0, 'decision': 'approve'}).status_code == 409
    assert not any(stored(service.NEGOTIATION, item['id'])['approvals'].values())


@pytest.mark.parametrize('change', ['approvals', 'status', 'buyer_id', 'preferences'])
def test_agent_cannot_mutate_identity_limits_or_finalize_a_deal(clients, monkeypatch, change):
    listing = create(clients[1])
    item = start(clients[0], listing)
    before = stored(service.NEGOTIATION, item['id'])
    def malicious(state, **kwargs):
        if change == 'approvals': state['approvals'] = {key: True for key in state['approvals']}
        if change == 'status': state['status'] = 'Confirmed'
        if change == 'buyer_id': state['buyer_id'] = USERS[2]
        if change == 'preferences': state['preferences']['maximum'] = '9999'
        return state
    monkeypatch.setattr(service.coordinator, 'advance', malicious)
    assert clients[0].post(f"/marketplace/negotiations/{item['id']}/advance", json={'version': 0}).status_code == 409
    assert stored(service.NEGOTIATION, item['id']) == before


def test_provider_errors_are_not_a_private_data_response_channel(clients, monkeypatch):
    from backend.agents.ollama_provider import OllamaProvider, ProviderError
    def unavailable(self, context):
        raise ProviderError('Synthetic upstream error containing private maximum 27.13')
    monkeypatch.setattr(OllamaProvider, 'decide', unavailable)
    listing = create(clients[1])
    item = start(clients[0], listing, provider='ollama')
    response = clients[0].post(f"/marketplace/negotiations/{item['id']}/advance", json={'version': 0})
    assert response.status_code == 200 and 'unavailable' in response.json()['error']
    assert '27.13' not in response.text and 'upstream' not in response.text
    assert response.json()['version'] == 1


@pytest.mark.parametrize('operation', ['edit', 'delete', 'start', 'advance', 'approve', 'cancel'])
def test_all_write_operations_require_a_user_token(clients, operation):
    listing = create(clients[1])
    item = start(clients[0], listing)
    with TestClient(app) as anonymous:
        if operation == 'edit': response = anonymous.put(f"/marketplace/listings/{listing['id']}", json=dict(listing_body(), version=0))
        elif operation == 'delete': response = anonymous.delete(f"/marketplace/listings/{listing['id']}?version=0")
        elif operation == 'start': response = anonymous.post('/marketplace/negotiations', json=preferences(listing))
        else: response = anonymous.post(f"/marketplace/negotiations/{item['id']}/{operation}", json={'version': 0, **({'decision': 'approve'} if operation == 'approve' else {})})
        assert response.status_code == 401


def test_missing_pickup_location_is_not_silently_filled_with_a_campus_default(clients):
    listing = create(clients[1])
    body = preferences(listing)
    del body['location']
    assert clients[0].post('/marketplace/negotiations', json=body).status_code == 422


def test_account_operations_do_not_rewrite_any_existing_demo_record(clients):
    def demo_snapshot():
        with Session() as db:
            return [(r.id, r.kind, copy.deepcopy(r.data)) for r in db.scalars(select(Record).where(Record.kind.in_(['student', 'session', 'listing', 'negotiation', 'migration'])).order_by(Record.id))]
    before = demo_snapshot()
    listing, item = pending(clients[0], clients[1])
    decision = clients[0].post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': item['version'], 'decision': 'reject'})
    assert decision.status_code == 200
    assert clients[1].delete(f"/marketplace/listings/{listing['id']}?version=0").status_code == 204
    assert demo_snapshot() == before


def test_stale_proposals_cannot_be_human_approved(clients):
    _, item = pending(clients[0], clients[1])
    # Simulates an out-of-band corrupt proposal. No API accepts these values.
    with Session() as db:
        record = db.get(Record, item['id'])
        data = copy.deepcopy(record.data)
        data['agreement']['price'] = '1'
        record.data = data
        db.commit()
    assert clients[0].post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': item['version'], 'decision': 'approve'}).status_code == 409
    assert not any(stored(service.NEGOTIATION, item['id'])['approvals'].values())


def test_approval_cancellation_race_has_only_one_terminal_result(clients):
    _, item = pending(clients[0], clients[1])
    item = clients[0].post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': item['version'], 'decision': 'approve'}).json()
    def operation(index):
        if index == 0: return clients[1].post(f"/marketplace/negotiations/{item['id']}/approve", json={'version': item['version'], 'decision': 'approve'})
        return clients[0].post(f"/marketplace/negotiations/{item['id']}/cancel", json={'version': item['version']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, [0, 1]))
    assert sorted(result.status_code for result in results) == [200, 409]
    latest = stored(service.NEGOTIATION, item['id'])
    assert latest['status'] in {'Confirmed', 'Cancelled'}
    finalized = [event for event in latest['audit_events'] if event['category'] == 'agreement_finalized']
    assert len(finalized) == (1 if latest['status'] == 'Confirmed' else 0)


def test_simultaneous_approval_requests_are_atomic_and_retryable(clients):
    _, item = pending(clients[0], clients[1])
    path = f"/marketplace/negotiations/{item['id']}/approve"
    def approve(client): return client.post(path, json={'version': item['version'], 'decision': 'approve'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, clients[:2]))
    assert sorted(r.status_code for r in results) == [200, 409]
    latest = clients[0].get(f"/marketplace/negotiations/{item['id']}").json()
    assert latest['status'] == 'Awaiting approvals' and sum(latest['approvals'].values()) == 1
    loser = 0 if results[0].status_code == 409 else 1
    final = clients[loser].post(path, json={'version': latest['version'], 'decision': 'approve'})
    assert final.status_code == 200 and final.json()['status'] == 'Confirmed'
    assert len([e for e in stored(service.NEGOTIATION, item['id'])['audit_events'] if e['category'] == 'agreement_finalized']) == 1


def test_simultaneous_advances_and_listing_edits_do_not_lose_updates(clients):
    listing = create(clients[1])
    def edit(title):
        with TestClient(app, headers=dict(clients[1].headers)) as client:
            return client.put(f"/marketplace/listings/{listing['id']}", json=dict(listing_body(title=title), version=0))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ['First complete update', 'Second complete update']))
    assert sorted(r.status_code for r in results) == [200, 409]
    listing = clients[1].get(f"/marketplace/listings/{listing['id']}/manage").json()
    item = start(clients[0], listing)
    def advance(client): return client.post(f"/marketplace/negotiations/{item['id']}/advance", json={'version': 0})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(advance, clients[:2]))
    assert sorted(r.status_code for r in results) == [200, 409]
    latest = stored(service.NEGOTIATION, item['id'])
    assert latest['version'] == 1 and latest['turn'] == 1 and len(latest['messages']) == 1


def test_independent_processes_cannot_finalize_or_overwrite_each_other(clients, tmp_path):
    _, item = pending(clients[0], clients[1])
    gate = tmp_path/'start'
    code = '''
import json,sys,time
from pathlib import Path
from fastapi import HTTPException
from backend.services.account_marketplace import human_decision
gate,ready,id,actor,version=sys.argv[1:]
Path(ready).touch()
deadline=time.monotonic()+20
while not Path(gate).exists():
    if time.monotonic()>deadline: raise RuntimeError('Test barrier timeout')
    time.sleep(.01)
try:
    result=human_decision(int(id),actor,int(version),'approve')
    print(json.dumps({'status':200,'version':result['version']}))
except HTTPException as error:
    print(json.dumps({'status':error.status_code}))
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(gate), str(tmp_path/f'ready-{i}'), str(item['id']), actor, str(item['version'])], cwd=ROOT, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i, actor in enumerate(USERS[:2])]
    try:
        deadline = time.monotonic()+20
        while not all((tmp_path/f'ready-{i}').exists() for i in range(2)):
            assert time.monotonic() < deadline
            time.sleep(.01)
        gate.touch()
        results = []
        for process in processes:
            output, error = process.communicate(timeout=20)
            assert process.returncode == 0, error
            results.append(json.loads(output))
        assert sorted(r['status'] for r in results) == [200, 409]
        latest = stored(service.NEGOTIATION, item['id'])
        assert latest['version'] == item['version']+1 and sum(latest['approvals'].values()) == 1
        loser = results.index(next(r for r in results if r['status'] == 409))
        final = service.human_decision(item['id'], USERS[loser], latest['version'], 'approve')
        assert final['status'] == 'Confirmed'
    finally:
        for process in processes:
            if process.poll() is None: process.kill(); process.wait()


@pytest.mark.parametrize('dialect', [sqlite.dialect(), postgresql.dialect()])
def test_versioned_updates_compile_for_both_database_dialects(dialect):
    statement = update(Record).where(Record.kind == service.NEGOTIATION, Record.data['version'].as_integer() == 3,
        Record.data['buyer_id'].as_string() == USERS[0]).values(data={'version': 4})
    compiled = str(statement.compile(dialect=dialect))
    assert 'UPDATE records' in compiled
    assert ('JSON_EXTRACT' in compiled) if dialect.name == 'sqlite' else ('->>' in compiled and 'CAST' in compiled)
