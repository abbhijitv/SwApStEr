import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from backend.agents import buyer_agent, seller_agent
from backend.agents.mock_provider import MockProvider
from backend.agents.ollama_provider import OllamaProvider, ProviderError
from backend.services.store import get, save, public_listing
from backend.models.schemas import Terms
from backend.agents.narration import render_message

def dt(s):
    parsed=datetime.fromisoformat(s.replace('Z','+00:00'))
    return parsed.astimezone(ZoneInfo('America/Phoenix')) if parsed.tzinfo else parsed
def fits(t,windows): return any(dt(w['start'])<=t<=dt(w['end']) for w in windows)
def public(n):
    from backend.services.students import student_by_id
    result = {k:v for k,v in n.items() if k not in ('preferences',)}
    for role in ('buyer', 'seller'):
        profile = student_by_id(n[role+'_id'])
        if profile: result[role] = profile['display_name']
    result['item'] = dict(n['item'], seller=result['seller'])
    return result
def initial_terms(p,l):
    # A buyer can consult the seller's PUBLIC pickup windows.
    candidates=[]
    for a in p['windows']:
        for b in l['windows']:
            start=max(dt(a['start']),dt(b['start']))
            end=min(dt(a['end']),dt(b['end']),dt(p['deadline']))
            preferred=start.replace(hour=17,minute=0)
            if start<=end: candidates.append(preferred if start<=preferred<=end else start)
    return {'price':p['target'],'pickup':min(candidates).isoformat(),'location':p['location'],'rental_days':p['rental_days']} if candidates else None

def valid_terms(t,p,l,role=None):
    price=Decimal(t['price']); pickup=dt(t['pickup'])
    if pickup.tzinfo is None or t['location']!=p['location']: return False
    if role in (None,'buyer'):
        if price>Decimal(p['maximum']) or not fits(pickup,p['windows']) or pickup>dt(p['deadline']): return False
        if t['rental_days']!=p['rental_days']: return False
    if role in (None,'seller'):
        if price<Decimal(l['minimum']) or price>Decimal(l['price']) or not fits(pickup,l['windows']): return False
        if l['type']=='Rent' and t['rental_days']!=l['rental_days']: return False
        if pickup+timedelta(days=t['rental_days'] if l['type']=='Rent' else 0)>dt(l['available_until']): return False
    return True

def advance(n):
    if n['status']=='Agreement proposed':
        n['status']='Awaiting approvals'
        n['version']+=1
        return save('negotiation',n,n['id'])
    if n['status']!='Negotiating': return n
    p=n['preferences']; l=get('listing',n['listing_id'])
    suggested=initial_terms(p,l)
    reason=None
    if not suggested: reason='No agreement — incompatible pickup schedules or academic deadline.'
    elif l['type']=='Rent' and p['rental_days']!=l['rental_days']: reason='No agreement — incompatible rental duration.'
    elif not valid_terms(dict(suggested,price=l['price']),p,l,'seller'): reason='No agreement — item availability does not cover the rental.'
    if reason:
        n.update(status='No agreement',reason=reason)
        return save('negotiation',n,n['id'])
    role='buyer' if len(n['messages'])%2==0 else 'seller'
    ctx=(buyer_agent.context(p,public_listing(l),n['messages'],n['offer'],suggested) if role=='buyer'
         else seller_agent.context(l,public_listing(l),n['messages'],n['offer'],n['offer'] or suggested))
    ctx['principal']={'id':n[role+'_id'],'display_name':public(n)[role]}
    provider=MockProvider() if n['provider']=='mock' else OllamaProvider()
    try: action=provider.decide(ctx)
    except ProviderError as e:
        n['error']=str(e); return save('negotiation',n,n['id'])
    n['error']=None
    t=action.terms.model_dump(mode='json') if action.terms else None
    invalid = action.action!='REJECT' and (not t or not valid_terms(t,p,l,role))
    if action.action=='ACCEPT' and (not n['offer'] or not t or Terms.model_validate(t)!=Terms.model_validate(n['offer'])): invalid=True
    prior=[m['terms'] for m in n['messages'] if m['role']==role and m.get('terms')]
    if t and prior and action.action in ('OFFER','COUNTER'):
        same_terms=Terms.model_validate(dict(t,price=prior[-1]['price']))==Terms.model_validate(prior[-1])
        if same_terms and (Decimal(t['price'])<Decimal(prior[-1]['price']) if role=='buyer' else Decimal(t['price'])>Decimal(prior[-1]['price'])):
            invalid=True
    if invalid:
        n['invalid_actions']=n.get('invalid_actions',0)+1
        if n['invalid_actions']>=2:
            n.update(status='No agreement',reason='No agreement — agent repeatedly proposed invalid terms.')
        else: n['error']='Agent proposed invalid terms. Server blocked them; retry or switch to mock.'
        return save('negotiation',n,n['id'])
    try:
        text=render_message(action.message,action.action,t,n['offer'])
    except ValueError:
        n['error']='Agent wording did not match safe public terms. Retry or explicitly switch to mock.'
        return save('negotiation',n,n['id'])
    if action.action=='ACCEPT':
        if not valid_terms(t,p,l):
            n.update(status='No agreement',reason='No agreement — incompatible price constraints.' if Decimal(p['maximum'])<Decimal(l['minimum']) else 'No agreement — incompatible terms.')
        else:
            n.update(status='Agreement proposed',agreement=dict(t,return_date=(dt(t['pickup'])+timedelta(days=t['rental_days'])).isoformat() if l['type']=='Rent' else None))
    elif action.action=='REJECT':
        n.update(status='No agreement',reason='No agreement — agent declined the terms.')
    else:
        n['offer']=t
    # Allow a justified hold, but terminate repeated unchanged offers instead of looping.
    if action.action in ('OFFER','COUNTER') and len(prior)>=2 and all(Terms.model_validate(x)==Terms.model_validate(t) for x in prior[-2:]):
        n.update(status='No agreement',reason='No agreement — incompatible price constraints.' if Decimal(p['maximum'])<Decimal(l['minimum']) else 'No agreement — repeated offers stalled the negotiation.')
    n['messages'].append({'role':role,'action':action.action,'text':text,'terms':t,'timestamp':datetime.now(timezone.utc).isoformat()})
    n['turn']=len(n['messages'])
    if n['turn']>=min(8,int(os.getenv('MAX_NEGOTIATION_TURNS','8'))) and n['status']=='Negotiating':
        n.update(status='No agreement',reason='No agreement — incompatible price constraints.' if Decimal(p['maximum'])<Decimal(l['minimum']) else 'No agreement — maximum negotiation turns reached.')
    n['version']+=1
    return save('negotiation',n,n['id'])
