"""Exercise real API enforcement and internal audits using isolated SQLite fixtures."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.schemas import Action
from backend.agents.mock_provider import MockProvider
from backend.services.store import get, save
from backend.services.audit import record_event
from backend.tests.test_negotiation import prefs, start, finish

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'})
        yield c

def pending(c):return finish(c,start(c))
def choose(c,student):
    r=c.post('/demo/session',json={'student':student});assert r.status_code==200
    return c.cookies.get('campus_session')
def audit(n):return get('negotiation',n['id'])['audit_events']
def assert_public(value):
    if isinstance(value,dict):
        assert not ({'maximum','minimum','preferences','audit_events'} & set(value))
        for child in value.values():assert_public(child)
    elif isinstance(value,list):
        for child in value:assert_public(child)

def test_private_limits_and_contexts_never_enter_public_responses_or_audit(client,monkeypatch):
    c=client;choose(c,'student-b')
    listing=c.get('/listings').json()[0]
    body={k:v for k,v in listing.items() if k not in ('id','seller','seller_id','icon')}
    body.update(title='Privacy fixture calculator',minimum='19.87')
    created=c.post('/listings',json=body);assert created.status_code==201
    listing=created.json();choose(c,'student-a')
    p=prefs(c);p.update(listing_id=listing['id'],maximum='27.13')
    contexts=[];original=MockProvider.decide
    def spy(self,ctx):contexts.append(copy.deepcopy(ctx));return original(self,ctx)
    monkeypatch.setattr(MockProvider,'decide',spy)
    n=finish(c,start(c,p));assert n['status']=='Awaiting approvals'
    assert get('listing',listing['id'])['minimum']=='19.87'
    assert get('negotiation',n['id'])['preferences']['maximum']=='27.13'
    for ctx in contexts:
        rendered=json.dumps(ctx)
        if ctx['role']=='buyer':assert 'minimum' not in rendered and '"19.87"' not in rendered
        else:assert 'maximum' not in rendered and '"27.13"' not in rendered
    for student in ('student-a','student-b'):
        choose(c,student)
        for path in ('/listings',f"/listings/{listing['id']}",'/negotiations',f"/negotiations/{n['id']}"):
            response=c.get(path);assert response.status_code==200
            assert_public(response.json())
            assert '"19.87"' not in response.text and '"27.13"' not in response.text
    events=audit(n)
    assert [e['category'] for e in events]==['offer_proposed','offer_proposed','offer_proposed','offer_accepted']
    assert '"19.87"' not in json.dumps(events) and '"27.13"' not in json.dumps(events)
    keys={'category','negotiation_id','turn','agent_role','action_type','public_price','validation_result','rejection_reason','timestamp'}
    for event in events:
        assert set(event)==keys and event['negotiation_id']==n['id']
        assert datetime.fromisoformat(event['timestamp']).tzinfo is not None

@pytest.mark.parametrize('role,price',[('buyer','999'),('seller','1'),('seller','999')])
def test_invalid_agent_price_is_blocked_and_not_copied_into_audit(client,monkeypatch,role,price):
    c=client;n=start(c)
    if role=='seller':n=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']}).json()
    before=copy.deepcopy(n)
    def invalid(self,ctx):
        return Action(action='COUNTER' if ctx['last_offer'] else 'OFFER',terms=dict(ctx['suggested_terms'],price=price),message='Would {price} work?')
    monkeypatch.setattr(MockProvider,'decide',invalid)
    response=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']});assert response.status_code==200
    n=response.json();assert n['turn']==before['turn'] and n['version']==before['version'] and not n['agreement']
    event=audit(n)[-1]
    assert event['category']=='constraint_violation' and event['rejection_reason']=='invalid_agent_terms'
    assert event['public_price'] is None
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409
    assert get('negotiation',n['id'])['status']!='Confirmed'

def test_incompatible_pickup_is_not_approvable_and_has_safe_audit(client):
    c=client;p=prefs(c)
    p['windows']=[{k:(datetime.fromisoformat(v)+timedelta(days=1)).isoformat() for k,v in w.items()} for w in p['windows']]
    n=finish(c,start(c,p));assert n['status']=='No agreement' and n['agreement'] is None
    assert audit(n)[-1]['rejection_reason']=='pickup_incompatible'
    for student in ('student-a','student-b'):
        choose(c,student)
        assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409
    assert get('negotiation',n['id'])['status']=='No agreement'

@pytest.mark.parametrize('corruption',[
    'missing_agreement','missing_accept','different_accepted_terms','missing_approval_key',
    'same_participant','non_boolean_approval','invalid_price','invalid_pickup',
    'incorrect_return','already_rejected','forged_outstanding_offer','wrong_owner',
])
def test_forged_pending_state_cannot_be_finalized(client,corruption):
    c=client;n=pending(c);raw=get('negotiation',n['id'])
    if corruption=='missing_agreement':raw['agreement']=None
    elif corruption=='missing_accept':raw['messages'][-1]['action']='COUNTER'
    elif corruption=='different_accepted_terms':raw['messages'][-1]['terms']['price']='24'
    elif corruption=='missing_approval_key':raw['approvals'].pop('student-b')
    elif corruption=='same_participant':raw['seller_id']=raw['buyer_id']
    elif corruption=='non_boolean_approval':raw['approvals']['student-b']='approved'
    elif corruption=='invalid_price':raw['agreement']['price']='999'
    elif corruption=='invalid_pickup':raw['agreement']['pickup']='2030-01-01T00:00:00-07:00'
    elif corruption=='incorrect_return':raw['agreement']['return_date']=raw['agreement']['pickup']
    elif corruption=='already_rejected':raw['rejected_by']='student-b'
    elif corruption=='forged_outstanding_offer':raw['offer']['price']='23'
    elif corruption=='wrong_owner':raw['seller_id']='student-c'
    save('negotiation',raw,n['id']);before=get('negotiation',n['id'])
    response=c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve','status':'Confirmed'})
    assert response.status_code==409,response.text
    after=get('negotiation',n['id'])
    assert after['status']=='Awaiting approvals' and after['approvals']==before['approvals']
    assert after['version']==before['version']
    assert after['audit_events'][-1]['rejection_reason']=='invalid_proposal'
    assert not any(e['category']=='agreement_finalized' for e in after['audit_events'])

@pytest.mark.parametrize('status',['Negotiating','Agreement proposed','No agreement','Rejected','Confirmed'])
def test_invalid_approval_state_has_no_transition(client,status):
    n=pending(client);raw=get('negotiation',n['id']);raw['status']=status;save('negotiation',raw,n['id'])
    r=client.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'})
    assert r.status_code==409
    after=get('negotiation',n['id']);assert after['status']==status and after['version']==raw['version']
    assert after['audit_events'][-1]['rejection_reason']=='invalid_state'

def test_unrelated_actor_and_duplicate_requests_only_add_safe_denial_events(client):
    n=pending(client);path=f"/negotiations/{n['id']}";v=n['version']
    choose(client,'student-c')
    assert client.post(path+'/approve',json={'decision':'approve','student':'student-a','role':'buyer'}).status_code==403
    raw=get('negotiation',n['id']);assert raw['version']==v and not any(raw['approvals'].values())
    assert raw['audit_events'][-1]['rejection_reason']=='unauthorized_participant'
    choose(client,'student-a');assert client.post(path+'/approve',json={'decision':'approve'}).status_code==200
    for _ in range(2):assert client.post(path+'/approve',json={'decision':'approve'}).status_code==409
    raw=get('negotiation',n['id'])
    assert raw['status']=='Awaiting approvals' and raw['version']==v+1
    assert sum(e['category']=='approval_recorded' for e in raw['audit_events'])==1
    assert not any(e['category']=='agreement_finalized' for e in raw['audit_events'])
    choose(client,'student-b');assert client.post(path+'/approve',json={'decision':'approve'}).json()['status']=='Confirmed'
    fresh=get('negotiation',n['id'])
    assert sum(e['category']=='approval_recorded' for e in fresh['audit_events'])==2
    assert sum(e['category']=='agreement_finalized' for e in fresh['audit_events'])==1
    assert_public(client.get(path).json())

def request_approval(token,id,decision='approve'):
    with TestClient(app) as c:
        c.cookies.set('campus_session',token)
        return c.post(f'/negotiations/{id}/approve',json={'decision':decision})

def test_concurrent_distinct_approvals_finalize_exactly_once(client):
    n=pending(client);buyer=client.cookies.get('campus_session');seller=choose(client,'student-b')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda token:request_approval(token,n['id']),[buyer,seller]))
    assert all(r.status_code==200 for r in results)
    assert {r.json()['status'] for r in results}=={'Awaiting approvals','Confirmed'}
    raw=get('negotiation',n['id'])
    assert raw['status']=='Confirmed' and all(raw['approvals'].values())
    assert sum(e['category']=='agreement_finalized' for e in raw['audit_events'])==1

def test_concurrent_duplicate_approvals_cannot_fill_other_participant_slot(client):
    n=pending(client);token=client.cookies.get('campus_session')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:request_approval(token,n['id']),range(4)))
    assert sorted(r.status_code for r in results)==[200,409,409,409]
    raw=get('negotiation',n['id'])
    assert raw['status']=='Awaiting approvals' and raw['approvals']=={'student-a':True,'student-b':False}
    assert raw['version']==n['version']+1
    assert sum(e['category']=='approval_recorded' for e in raw['audit_events'])==1
    assert not any(e['category']=='agreement_finalized' for e in raw['audit_events'])

def test_concurrent_approve_and_reject_have_only_one_terminal_winner(client):
    n=pending(client);client.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'});seller=choose(client,'student-b')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda decision:request_approval(seller,n['id'],decision),['approve','reject']))
    assert sorted(r.status_code for r in results)==[200,409]
    winner=next(r.json()['status'] for r in results if r.status_code==200)
    raw=get('negotiation',n['id']);assert raw['status']==winner
    assert winner in ('Rejected','Confirmed')
    assert sum(e['category']=='agreement_finalized' for e in raw['audit_events'])==(1 if winner=='Confirmed' else 0)
    assert sum(e['rejection_reason']=='student_rejected' for e in raw['audit_events'])==(1 if winner=='Rejected' else 0)

def test_audit_rejects_arbitrary_text_and_invalid_price_fields():
    n={'id':123,'turn':0}
    with pytest.raises(ValueError):record_event(n,'constraint_violation',role='buyer',action='OFFER',result='rejected',reason='My private budget is secret')
    with pytest.raises(ValueError):record_event(n,'constraint_violation',role='buyer',action='OFFER',result='rejected',reason='invalid_agent_terms',public_price='27.13')
    assert 'audit_events' not in n

def test_hosted_public_demo_still_works_but_judge_cannot_expose_limits(client,monkeypatch):
    n=pending(client)
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('PUBLIC_DEMO_MODE','true');monkeypatch.setenv('ENABLE_JUDGE_MODE','true')
    assert client.get('/demo/session').status_code==200
    assert client.get('/students').status_code==200
    assert_public(client.get(f"/negotiations/{n['id']}").json())
    assert client.get(f"/demo/judge/{n['id']}").status_code==403

def test_audit_does_not_copy_malformed_turn_metadata():
    n={'id':123,'turn':'private context must not be copied'}
    event=record_event(n,'constraint_violation',role='coordinator',action='APPROVE',result='rejected',reason='invalid_proposal')
    assert event['turn'] is None and 'private context' not in json.dumps(event)

def test_stall_has_a_structured_terminal_audit_event(client,monkeypatch):
    def hold(self,c):
        return Action(action='COUNTER' if c['last_offer'] else 'OFFER',terms=dict(c['suggested_terms'],price='15' if c['role']=='buyer' else '35'),message='I am holding at {price}; would that work?')
    monkeypatch.setattr(MockProvider,'decide',hold)
    n=finish(client,start(client))
    assert n['status']=='No agreement'
    assert audit(n)[-1]['rejection_reason']=='stalled'
    assert not any(e['category']=='agreement_finalized' for e in audit(n))

def test_stale_advance_records_safe_denial_without_advancing_again(client):
    n=start(client);path=f"/negotiations/{n['id']}"
    first=client.post(path+'/advance',json={'version':0}).json()
    assert client.post(path+'/advance',json={'version':0}).status_code==409
    raw=get('negotiation',n['id'])
    assert raw['turn']==first['turn'] and raw['version']==first['version']
    assert raw['audit_events'][-1]['rejection_reason']=='stale_version'
    assert raw['audit_events'][-1]['public_price'] is None
