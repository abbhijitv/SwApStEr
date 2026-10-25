from copy import deepcopy
from decimal import Decimal
import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.store import get, save
from backend.agents.negotiation_coordinator import valid_terms
from backend.agents.ollama_provider import OllamaProvider
from backend.agents.mock_provider import MockProvider

@pytest.fixture
def housing():
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-b'})
        body={'title':'Summer room near campus','description':'A furnished summer room near the university.', 'category':'Housing & Subleases','price':'900','minimum':'750','housing':{'listing_type':'Private room sublease','neighborhood':'Tempe campus','lease_start':'2027-05-15','lease_end':'2027-08-15','furnished':True,'utilities_included':True,'bedrooms':1,'bathrooms':1,'roommate_info':'One student roommate'}}
        r=c.post('/listings',json=body); assert r.status_code==201,r.text
        listing=r.json()
        c.post('/demo/session',json={'student':'student-a'})
        prefs={'listing_id':listing['id'],'maximum':'850','provider':'mock','housing':{'desired_move_in':'2027-06-01','desired_move_out':'2027-08-01'}}
        yield c,body,listing,prefs

def finish(c,p):
    r=c.post('/negotiations',json=p); assert r.status_code==201,r.text
    n=r.json()
    for _ in range(10):
        if n['status'] not in ('Negotiating','Agreement proposed'):break
        n=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']}).json()
    return n

def test_housing_success_and_approvals(housing):
    c,body,l,p=housing
    assert c.get(f"/listings/{l['id']}").json()['housing']==body['housing']
    assert 'minimum' not in l
    n=finish(c,p)
    assert n['status']=='Awaiting approvals',n
    assert Decimal('750')<=Decimal(n['agreement']['price'])<=Decimal('850')
    assert n['agreement']['lease_start']=='2027-06-01'
    assert n['agreement']['lease_end']=='2027-08-01'
    assert n['agreement']['return_date'] is None
    assert all('/month' in m['text'] and 'pickup' not in m['text'] for m in n['messages'])
    assert 'preferences' not in n and 'audit_events' not in n
    assert 'minimum' not in json.dumps(n) and 'maximum' not in json.dumps(n)
    stored=get('negotiation',n['id'])
    assert stored['preferences']['maximum']=='850'
    assert all(e.get('public_price') not in ('850','850.00','750','750.00') for e in stored['audit_events'])
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Awaiting approvals'
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409
    c.post('/demo/session',json={'student':'student-c'})
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==403
    c.post('/demo/session',json={'student':'student-b'})
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Confirmed'

@pytest.mark.parametrize('change',[{'maximum':'700'},{'housing':{'desired_move_in':'2027-05-01','desired_move_out':'2027-08-01'}},{'housing':{'desired_move_in':'2027-06-01','desired_move_out':'2027-09-01'}},{'housing':{'desired_move_in':'2027-06-01','desired_move_out':'2027-08-01','furnished':False}}])
def test_incompatible_housing(housing,change):
    c,_,_,p=housing;p.update(change)
    n=finish(c,p); assert n['status']=='No agreement',n
    assert n['agreement'] is None
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409

@pytest.mark.parametrize('field,value',[('lease_end','2027-05-14'),('bedrooms',0),('bathrooms',-1)])
def test_invalid_housing_listing(housing,field,value):
    c,body,_,_=housing;body['housing'][field]=value
    assert c.post('/listings',json=body).status_code==422

@pytest.mark.parametrize('field,value',[('price','-1'),('price','NaN'),('minimum','901')])
def test_invalid_rent(housing,field,value):
    c,body,_,_=housing;body[field]=value
    assert c.post('/listings',json=body).status_code==422

def test_invalid_buyer_dates(housing):
    c,_,_,p=housing;p['housing']['desired_move_out']='2027-05-01'
    assert c.post('/negotiations',json=p).status_code==422

@pytest.mark.parametrize('change',[{'price':'900'},{'price':'749'},{'lease_start':'2027-05-30'},{'lease_end':'2027-08-02'},{'location':'Other neighborhood'}])
def test_forged_housing_agreement_blocked(housing,change):
    c,_,l,p=housing;n=finish(c,p)
    saved=get('negotiation',n['id']);saved['agreement'].update(change)
    # Even a mutually consistent forged transcript cannot bypass current constraints.
    saved['offer']=deepcopy(saved['agreement'])
    for m in saved['messages'][-2:]:m['terms']=deepcopy(saved['agreement'])
    save('negotiation',saved,n['id'])
    assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).status_code==409

def test_flexible_move_in(housing):
    c,_,_,p=housing;p['housing'].update(desired_move_in='2027-05-13',move_in_flex_days=2)
    n=finish(c,p)
    assert n['status']=='Awaiting approvals'
    assert n['agreement']['lease_start']=='2027-05-15'

def test_housing_ollama_pipeline_public_narration(housing,monkeypatch):
    c,_,_,p=housing;p['provider']='ollama'
    monkeypatch.setattr(OllamaProvider,'decide',lambda self,ctx:MockProvider().decide(ctx))
    contexts=[]
    def narrate(self,ctx):
        contexts.append(ctx)
        assert 'maximum' not in json.dumps(ctx) and 'minimum' not in json.dumps(ctx)
        return ('At {price}/month from {lease_start} through {lease_end}, these terms work for me; both students can review.' if ctx['action']=='ACCEPT' else 'Would {price}/month work from {lease_start} through {lease_end}?'),'ollama'
    monkeypatch.setattr(OllamaProvider,'narrate',narrate)
    assert finish(c,p)['status']=='Awaiting approvals'
    assert contexts and all(ctx['item']['housing'] for ctx in contexts)

@pytest.mark.parametrize('price',['851','749'])
def test_llm_cannot_bypass_housing_price_limits(housing,monkeypatch,price):
    from backend.models.schemas import Action
    c,_,_,p=housing;p['provider']='ollama'
    def decide(self,ctx):
        # Buyer above budget, or seller below its own minimum.
        if price=='749' and ctx['role']=='buyer':return MockProvider().decide(ctx)
        return Action(action='COUNTER' if ctx['last_offer'] else 'OFFER',terms=dict(ctx['suggested_terms'],price=price))
    monkeypatch.setattr(OllamaProvider,'decide',decide)
    monkeypatch.setattr(OllamaProvider,'narrate',lambda self,ctx:('Would {price}/month work from {lease_start} through {lease_end}?','ollama'))
    n=finish(c,p)
    assert n['status']=='No agreement' and n['agreement'] is None
    assert all(m['terms']['price']!=price for m in n['messages'])

def test_ollama_housing_decision_schema_and_private_context(housing,monkeypatch):
    from backend.agents import buyer_agent,seller_agent
    from backend.agents.housing import compatible
    from backend.models.schemas import Preferences
    c,_,l,p=housing
    p=Preferences.model_validate(p).model_dump(mode='json')
    listing=get('listing',l['id']);suggested=compatible(p,listing)
    buyer=buyer_agent.context(p,l,[],None,suggested)
    seller=seller_agent.context(listing,l,[],None,suggested)
    assert 'minimum' not in json.dumps(buyer)
    assert 'maximum' not in json.dumps(seller) and 'requirements' not in json.dumps(seller)
    def generate(self,prompt,schema,*args,**kwargs):
        terms=schema['$defs']['Terms']
        assert 'lease_start' in terms['required'] and 'pickup' not in terms['properties']
        assert 'MONTHLY RENT' in prompt
        return json.dumps({'action':'OFFER','terms':suggested})
    monkeypatch.setattr(OllamaProvider,'generate',generate)
    assert OllamaProvider().decide(buyer).terms.transaction=='housing'

@pytest.mark.parametrize('message',[
 'Your offer of {price}/month is accepted for {lease_start} through {lease_end}.',
 'I propose {price} for {lease_start} through {lease_end}.',
 'This signed lease costs {price}/month for {lease_start} through {lease_end}.',
 'Would {price}/month work for pickup on {lease_start}?',
])
def test_housing_narration_rejects_false_or_wrong_units(message):
    from backend.agents.narration import validate_narration, NarrationError
    context={'role':'buyer','action':'OFFER','terms':{'price':'780','transaction':'housing','lease_start':'2027-06-01','lease_end':'2027-08-01','location':'Tempe campus'},'previous_offer':None,'item':{'type':'Rent','housing':True},'conversation':[]}
    with pytest.raises(NarrationError):validate_narration(message,context)

def test_housing_narration_does_not_repeat_public_messages():
    from backend.agents.narration import validate_narration, NarrationError
    terms={'price':'780','transaction':'housing','lease_start':'2027-06-01','lease_end':'2027-08-01','location':'Tempe campus'}
    context={'role':'seller','action':'COUNTER','terms':terms,'previous_offer':terms,'item':{'type':'Rent','housing':True},'conversation':[{'text':'Would $780/month work?'}]}
    with pytest.raises(NarrationError):validate_narration('Would {price}/month work?',context)

def test_fractional_monthly_rent_counters_are_valid_currency(housing):
    c,_,l,p=housing
    listing=get('listing',l['id']);listing.update(price='900.55',minimum='810.52')
    save('listing',listing,l['id'])
    n=finish(c,p)
    assert n['status']=='Awaiting approvals',n
    assert Decimal('810.52')<=Decimal(n['agreement']['price'])<=Decimal('850')
