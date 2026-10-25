from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.store import get
from backend.agents import buyer_agent, seller_agent
from backend.agents.mock_provider import MockProvider
from backend.models.schemas import Action
from backend.agents.ollama_provider import OllamaProvider, ProviderError

@pytest.fixture
def c():
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'})
        yield c

def prefs(c, index=0):
    l=c.get('/listings').json()[index]
    return {'listing_id':l['id'],'target':'15','maximum':'25','rental_days':3,
      'windows':l['windows'],'deadline':l['available_until'],'location':'Hayden Library','provider':'mock'}
def start(c,p=None):
    r=c.post('/negotiations',json=p or prefs(c)); assert r.status_code==201,r.text
    return r.json()
def finish(c,n):
    for _ in range(9):
        if n['status'] not in ('Negotiating','Agreement proposed'): break
        r=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']})
        assert r.status_code==200,r.text
        n=r.json()
    return n

def test_complete_integration(c):
    c.post('/demo/session',json={'student':'student-b'})
    l=c.get('/listings').json()[0]
    body={k:v for k,v in l.items() if k not in ('id','seller','seller_id','icon')}
    body.update(title='Integration calculator',minimum='20')
    r=c.post('/listings',json=body); assert r.status_code==201,r.text
    c.post('/demo/session',json={'student':'student-a'})
    p=prefs(c); p['listing_id']=r.json()['id']
    n=finish(c,start(c,p))
    assert n['status']=='Awaiting approvals'
    assert Decimal('20')<=Decimal(n['agreement']['price'])<=Decimal('25')
    assert len(n['messages'])>=4
    assert n['agreement']['return_date']
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Awaiting approvals'
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409
    c.post('/demo/session',json={'student':'student-b'})
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Confirmed'
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'reject'}).status_code==409

def test_impossible(c):
    n=finish(c,start(c,prefs(c,5)))
    assert n['status']=='No agreement'
    assert 'incompatible price' in n['reason']
    assert n['turn']<=8
    assert n['agreement'] is None
    for m in n['messages']:
        p=Decimal(m['terms']['price'])
        assert p<=25 if m['role']=='buyer' else p>=50

def test_private_isolation(c):
    n=start(c); raw=get('negotiation',n['id']); l=get('listing',n['listing_id'])
    assert 'preferences' not in n and 'minimum' not in n['item']
    b=buyer_agent.context(raw['preferences'],n['item'],[],None,{})
    s=seller_agent.context(l,n['item'],[],None,{})
    assert 'minimum' not in str(b)
    assert 'maximum' not in str(s) and 'target' not in str(s)
    assert 'preferences' not in c.get(f"/negotiations/{n['id']}").json()
    assert c.get(f"/demo/judge/{n['id']}").status_code==403

def test_scheduling(c):
    p=prefs(c); p['windows']=[{'start':'2030-01-01T10:00:00-07:00','end':'2030-01-01T12:00:00-07:00'}]
    n=finish(c,start(c,p)); assert n['status']=='No agreement'; assert 'pickup' in n['reason']
def test_rental_duration(c):
    p=prefs(c); p['rental_days']=5
    assert finish(c,start(c,p))['status']=='No agreement'
def test_rejection(c):
    n=finish(c,start(c)); r=c.post(f"/negotiations/{n['id']}/approve",json={'decision':'reject'})
    assert r.json()['status']=='Rejected'
    c.post('/demo/session',json={'student':'student-b'})
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409

def test_auth_and_invalid(c):
    assert c.post('/negotiations',json={}).status_code==422
    p=prefs(c); p['target']='99'
    assert c.post('/negotiations',json=p).status_code==422
    assert TestClient(app).get('/negotiations').status_code==401
    assert c.post('/demo/session',json={'student':'admin'}).status_code==404
    n=start(c)
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409

def test_duplicate_advance(c):
    n=start(c)
    assert c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).status_code==200
    assert c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).status_code==409

def test_invalid_model_actions_blocked(c,monkeypatch):
    monkeypatch.setattr(MockProvider,'decide',lambda self,ctx: Action(action='OFFER',terms={'price':'999','pickup':ctx['suggested_terms']['pickup'],'rental_days':3,'location':'Library'}))
    n=start(c)
    for _ in range(2): n=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
    assert n['status']=='No agreement' and n['agreement'] is None

def test_malformed_ollama(monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self): return {'response':'not json'}
    calls=[]
    def fake(*a,**k): calls.append(k); return R()
    monkeypatch.setattr('httpx.post',fake)
    with pytest.raises(ProviderError): OllamaProvider().decide({'role':'buyer'})
    assert len(calls)==2

def test_turn_limit(c,monkeypatch):
    monkeypatch.setenv('MAX_NEGOTIATION_TURNS','2')
    n=finish(c,start(c)); assert n['turn']==2 and n['status']=='No agreement'

def test_no_silent_fallback(c,monkeypatch):
    def fail(*args): raise ProviderError('Ollama unavailable')
    monkeypatch.setattr(OllamaProvider,'decide',fail)
    p=prefs(c);p['provider']='ollama';n=start(c,p)
    n=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
    assert n['provider']=='ollama' and n['error'] and not n['messages']
    assert c.post(f"/negotiations/{n['id']}/mock").json()['provider']=='mock'

def test_browser_utc_dates(c):
    from datetime import datetime, timezone
    p=prefs(c)
    p['windows']=[{k:datetime.fromisoformat(v).astimezone(timezone.utc).isoformat().replace('+00:00','Z') for k,v in w.items()} for w in p['windows']]
    n=finish(c,start(c,p))
    assert n['status']=='Awaiting approvals'
    assert '17:00:00-07:00' in n['agreement']['pickup']

def test_seller_minimum_blocks_model(c,monkeypatch):
    n=start(c)
    n=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
    def bad(self,ctx):
        return Action(action='COUNTER',terms=dict(ctx['suggested_terms'],price='1'))
    monkeypatch.setattr(MockProvider,'decide',bad)
    r=c.post(f"/negotiations/{n['id']}/advance",json={'version':1}).json()
    assert r['error'] and r['agreement'] is None and len(r['messages'])==1

def test_accept_must_match_public_offer(c,monkeypatch):
    n=start(c);n=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
    def bad(self,ctx): return Action(action='ACCEPT',terms=dict(ctx['suggested_terms'],price='22'))
    monkeypatch.setattr(MockProvider,'decide',bad)
    r=c.post(f"/negotiations/{n['id']}/advance",json={'version':1}).json()
    assert r['error'] and r['agreement'] is None

def test_cookie_controls_approval_role(c):
    n=finish(c,start(c))
    r=c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve','student':'student-b','role':'seller'}).json()
    assert r['approvals']['student-a'] and not r['approvals']['student-b']

def test_judge_opt_in_and_production(c,monkeypatch):
    n=start(c)
    monkeypatch.setenv('ENABLE_JUDGE_MODE','true')
    assert c.get(f"/demo/judge/{n['id']}").json()['buyer_private']['maximum']=='25'
    monkeypatch.setenv('APP_ENV','production')
    assert c.get(f"/demo/judge/{n['id']}").status_code==403
    assert c.post('/demo/session',json={'student':'student-a'}).status_code==403
    assert c.get('/negotiations').status_code==403

def test_ollama_repairs_own_price_violation(monkeypatch):
    import json
    replies=iter(['18','20']);prompts=[]
    class R:
        def __init__(self,response):self.response=response
        def raise_for_status(self):pass
        def json(self):return {'response':json.dumps(self.response)}
    def fake(*args,**kwargs):
        prompt=kwargs['json']['prompt'];prompts.append(prompt)
        if 'public negotiation' in prompt:return R({'message':'Thanks for the offer! Could you do {price} for {duration}?'})
        return R({'action':'COUNTER','terms':{'price':next(replies),'pickup':'2026-10-28T17:00:00-07:00','location':'Hayden Library','rental_days':3}})
    monkeypatch.setattr('httpx.post',fake)
    a=OllamaProvider().decide({'role':'seller','own_turn':1,'last_offer':{'price':'15','pickup':'2026-10-28T17:00:00-07:00','location':'Hayden Library','rental_days':3},'private':{'minimum':'20','price':'35'}})
    assert a.terms.price==20 and len(prompts)==2 and a.message is None
    assert 'Correction' in prompts[1]

def test_proposal_state_precedes_approvals(c):
    n=start(c)
    for _ in range(4): n=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']}).json()
    assert n['status']=='Agreement proposed' and n['turn']==4
    n=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']}).json()
    assert n['status']=='Awaiting approvals' and n['turn']==4
