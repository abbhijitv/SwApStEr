"""Phase 1: validated decisions cannot fail solely because of public wording."""
import json
import logging
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.agents.ollama_provider import OllamaProvider,ProviderError
from backend.agents.narration import validate_narration,neutral_message,render_message
from backend.models.schemas import Action
from backend.tests.test_negotiation import prefs,start,finish

T={'price':'20','pickup':'2026-10-28T17:00:00-07:00','location':'Hayden Library','rental_days':3}
def public_context(kind='Rent',action='OFFER',history=None):
    return {'role':'buyer','action':action,'terms':dict(T),'previous_offer':None,
            'item':{'title':'Academic textbook' if kind=='Buy' else 'Calculator','type':kind},'conversation':history or []}

@pytest.mark.parametrize('kind',['Buy','Rent'])
@pytest.mark.parametrize('action',['OFFER','COUNTER','ACCEPT','REJECT'])
def test_safe_presentation_fallback_preserves_action_and_terms(kind,action):
    c=public_context(kind,action);before=json.dumps(c,sort_keys=True)
    text=render_message(neutral_message(c),action,T)
    assert json.dumps(c,sort_keys=True)==before
    assert 'maximum' not in text and 'minimum' not in text
    if action!='REJECT':assert '$20' in text
    if kind=='Buy':assert 'days' not in text and 'rent' not in text and 'return' not in text
    assert 'confirmed' not in text

def test_narration_repair_is_bounded_and_falls_back(caplog,monkeypatch):
    calls=[]
    def bad(self,prompt,schema,tokens=200,temperature=0):calls.append(prompt);return json.dumps({'message':'Your secret minimum is $99; deal confirmed.'})
    monkeypatch.setattr(OllamaProvider,'generate',bad)
    with caplog.at_level(logging.WARNING):message,source=OllamaProvider().narrate(public_context())
    assert len(calls)==2 and source=='safe_fallback'
    assert 'Repair:' in calls[1]
    assert '$99' not in caplog.text and 'secret minimum' not in caplog.text
    assert '$20' in render_message(message,'OFFER',T)

def test_narration_repairs_opening_context_and_transaction_type(monkeypatch):
    replies=iter([{'message':'Your offer sounds good. I can rent it for {duration} at {price}.'},
                  {'message':'Hi! Would you consider {price} for this textbook?'}])
    prompts=[]
    def generate(self,prompt,*args,**kwargs):prompts.append(prompt);return json.dumps(next(replies))
    monkeypatch.setattr(OllamaProvider,'generate',generate)
    message,source=OllamaProvider().narrate(public_context('Buy'))
    assert source=='ollama' and len(prompts)==2 and 'FIRST message' in prompts[0]
    assert 'rental_days' not in prompts[0]
    assert 'rent' not in message and 'previous offer' not in message

@pytest.mark.parametrize('message',[
    'Your offer sounds good. Would {price} work?',
    'Thanks for the offer. Could we do {price}?',
    'Can I rent this book for {duration} at {price}?',
    'I can pay {price} and return it later.',
])
def test_incorrect_purchase_openings_rejected(message):
    with pytest.raises(ValueError):validate_narration(message,public_context('Buy'))

def test_generic_rental_language_is_not_a_numeric_contradiction():
    c=public_context(history=[{'role':'seller','text':'Would this work?'}]);c['action']='COUNTER'
    assert validate_narration('Could we meet at {price}? The rental days and pickup work for me.',c)

def test_only_validated_decisions_reach_narration(monkeypatch):
    narrated=[]
    def invalid(self,c):return Action(action='OFFER',terms=dict(T,price='999'))
    monkeypatch.setattr(OllamaProvider,'decide',invalid)
    monkeypatch.setattr(OllamaProvider,'narrate',lambda self,c:narrated.append(c))
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'});p=prefs(c);p['provider']='ollama';n=start(c,p)
        blocked=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
        assert blocked['error'] and not narrated and not blocked['agreement'] and not blocked['messages']

def test_valid_ollama_decision_survives_bad_narration_and_still_needs_both_approvals(monkeypatch):
    # Use fixed decisions only in this unit test to exercise the narration failure boundary.
    from backend.agents.mock_provider import MockProvider
    monkeypatch.setattr(OllamaProvider,'decide',lambda self,c:MockProvider().decide(c))
    monkeypatch.setattr(OllamaProvider,'generate',lambda *args,**kwargs:'not JSON')
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'});p=prefs(c);p['provider']='ollama'
        n=finish(c,start(c,p))
        assert n['status']=='Awaiting approvals' and n['provider']=='ollama'
        assert all(m['narration_source']=='safe_fallback' for m in n['messages'])
        assert not any(n['approvals'].values())
        assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Awaiting approvals'
        c.post('/demo/session',json={'student':'student-b'})
        assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Confirmed'

def test_purchase_mock_proposal_has_no_rental_narrative_or_return_deadline():
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'})
        p=prefs(c,3);p.update(target='20',maximum='30')
        n=finish(c,start(c,p))
        assert n['status']=='Awaiting approvals' and n['item']['type']=='Buy'
        assert n['agreement']['return_date'] is None
        assert all('days' not in m['text'] and 'rent' not in m['text'] and 'return' not in m['text'] for m in n['messages'])

def test_public_role_prefix_removed_and_purchase_not_relabelled_as_listed_price():
    c=public_context()
    assert validate_narration('OFFER: Would {price} work for {duration}?',c)=='Would {price} work for {duration}?'
    with pytest.raises(ValueError):validate_narration('It looks priced at {price}. Do you accept? ',public_context('Buy'))

def test_verbatim_public_copy_is_repaired_or_falls_back():
    c=public_context(action='ACCEPT',history=[{'role':'seller','text':'REPLY: $20 works for me. Let’s send the terms for student review.'}])
    with pytest.raises(ValueError):validate_narration('{price} works for me. Let’s send the terms for student review.',c)

def test_buyer_does_not_bid_above_public_asking_price():
    from backend.agents.mock_provider import MockProvider
    action=MockProvider().decide({'role':'buyer','own_turn':0,'private':{'target':'15','maximum':'25'},
        'listing':{'price':'10','type':'Buy'},'last_offer':None,'suggested_terms':dict(T),'history':[]})
    assert action.terms.price==10
