import json
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.agents.mock_provider import MockProvider
from backend.agents.ollama_provider import OllamaProvider
from backend.agents.narration import render_message
from backend.models.schemas import Action
from backend.tests.test_negotiation import start,finish

T={'price':'21.50','pickup':'2026-10-28T17:00:00-07:00','location':'Hayden Library','rental_days':3}

def test_public_words_use_validated_facts():
    text=render_message('Thanks! Would {price} work for {duration}? I can meet at {location} on {pickup}.','COUNTER',T)
    assert '$21.50' in text and '3 days' in text and 'Wednesday at 5:00 PM' in text and '{' not in text

@pytest.mark.parametrize('text',[
 'My maximum is twenty five, but would {price} work?',
 'I can pay $99 for {duration}.',
 'How about {price} for five days?',
 'I accept {price}; your deal is confirmed.',
 'Would {hidden_budget} work instead of {price}?',
])
def test_unsafe_or_inconsistent_public_words_are_blocked(text):
    with pytest.raises(ValueError):render_message(text,'ACCEPT',T)

def test_seller_cannot_exceed_asking_price(monkeypatch):
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'});n=start(c)
        n=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
        def inflated(self,ctx):return Action(action='COUNTER',terms=dict(ctx['suggested_terms'],price='45'),message='Could you do {price}?')
        monkeypatch.setattr(MockProvider,'decide',inflated)
        blocked=c.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']}).json()
        assert blocked['error'] and blocked['turn']==1 and not blocked['agreement']

def test_contextual_mock_exchange_and_facts():
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'});n=finish(c,start(c))
        assert n['status']=='Awaiting approvals'
        messages=n['messages']
        assert len({m['text'] for m in messages})==len(messages)
        for m in messages:
            assert '$'+format(Decimal(m['terms']['price']),'.2f').removesuffix('.00') in m['text']
            assert 'maximum' not in m['text'] and 'minimum' not in m['text'] and '{' not in m['text']
        assert messages[-1]['action']=='ACCEPT'

def test_repeated_offers_stop_without_fabricating_agreement(monkeypatch):
    def hold(self,ctx):
        price='15' if ctx['role']=='buyer' else '35'
        return Action(action='COUNTER' if ctx['last_offer'] else 'OFFER',terms=dict(ctx['suggested_terms'],price=price),message='I’m holding at {price}; does that still work for you?')
    monkeypatch.setattr(MockProvider,'decide',hold)
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'})
        n=finish(c,start(c))
        assert n['status']=='No agreement' and 'stalled' in n['reason'] and n['turn']<=8 and not n['agreement']

def test_ollama_public_writer_has_no_private_context(monkeypatch):
    prompts=[]
    class R:
        def __init__(self,data):self.data=data
        def raise_for_status(self):pass
        def json(self):return {'response':json.dumps(self.data)}
    def generate(*args,**kwargs):
        prompt=kwargs['json']['prompt'];prompts.append(prompt)
        if 'validated public action' in prompt:return R({'message':'Thanks for considering it. Would {price} work for {duration}?'})
        return R({'action':'OFFER','terms':T})
    monkeypatch.setattr('httpx.post',generate)
    provider=OllamaProvider()
    a=provider.decide({'role':'buyer','own_turn':0,'private':{'target':'15','maximum':'24.73'},'history':[],'last_offer':None,'listing':{'title':'Academic calculator','type':'Rent'}})
    assert a.message is None and len(prompts)==1
    message,source=provider.narrate({'role':'buyer','action':a.action,'terms':a.terms.model_dump(mode='json'),'previous_offer':None,'item':{'title':'Academic calculator','type':'Rent'},'conversation':[]})
    assert len(prompts)==2 and message and source=='ollama'
    assert '24.73' in prompts[0] and '24.73' not in prompts[1]
    assert '"private"' not in prompts[1] and '"maximum"' not in prompts[1]

def test_equivalent_natural_price_duration_and_time_formats_are_bound():
    text=render_message('Would $21.50 work for three days? I can meet at Hayden Library on Wednesday at 5 PM.','COUNTER',T)
    assert text=='Would $21.50 work for 3 days? I can meet at Hayden Library on Wednesday at 5:00 PM.'
    with pytest.raises(ValueError):render_message('Would $21.51 work for three days?','COUNTER',T)

def test_location_cannot_carry_unvalidated_private_text(monkeypatch):
    with TestClient(app) as c:
        c.post('/demo/session',json={'student':'student-a'});n=start(c)
        def unsafe(self,ctx):return Action(action='OFFER',terms=dict(ctx['suggested_terms'],location='My private maximum is disclosed here'),message='Would {price} work at {location}?')
        monkeypatch.setattr(MockProvider,'decide',unsafe)
        blocked=c.post(f"/negotiations/{n['id']}/advance",json={'version':0}).json()
        assert blocked['error'] and not blocked['messages'] and not blocked['agreement']

def test_response_can_acknowledge_only_actual_previous_shared_price():
    previous=dict(T,price='15')
    text=render_message('Thanks for offering $15. Could you consider $21.50 for three days?','COUNTER',T,previous)
    assert text=='Thanks for offering $15. Could you consider $21.50 for 3 days?'
    with pytest.raises(ValueError):render_message('Thanks for offering $99. Could you consider $21.50?','COUNTER',T,previous)
    with pytest.raises(ValueError):render_message('I like {previous_price}, but could we do {price}?','COUNTER',T)
