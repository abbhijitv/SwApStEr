import json
import os
import threading
import logging
from decimal import Decimal
import httpx
from backend.models.schemas import Action, Terms
from backend.agents.narration import validate_message, bind_public_facts

INFERENCE_LOCK=threading.Lock()
class ProviderError(Exception):
    pass

class OllamaProvider:
    def generate(self,prompt,schema,tokens=200):
        response=httpx.post(os.getenv('OLLAMA_BASE_URL','http://localhost:11434')+'/api/generate',
            json={'model':os.getenv('OLLAMA_MODEL','qwen2.5:3b'),'prompt':prompt,'stream':False,
                  'format':schema,'keep_alive':'5m',
                  'options':{'temperature':0.25,'num_predict':tokens,'num_ctx':2048}},timeout=90)
        response.raise_for_status()
        return response.json()['response']

    def decide(self,context):
        own=context.get('private',{});buyer=context['role']=='buyer'
        floor=Decimal('0.01') if buyer else Decimal(own.get('minimum','0.01'))
        ceiling=Decimal(own.get('maximum','999999')) if buyer else Decimal(own.get('price','999999'))
        own_offers=[m['terms'] for m in context.get('history',[]) if m['role']==context['role'] and m.get('terms')]
        if own_offers:
            if buyer:floor=max(floor,Decimal(own_offers[-1]['price']))
            else:ceiling=min(ceiling,Decimal(own_offers[-1]['price']))
        last=context.get('last_offer')
        allowed=['OFFER' if not last else 'COUNTER']
        if last and floor<=Decimal(last['price'])<=ceiling:allowed.append('ACCEPT')
        if context.get('own_turn',0)>=3:allowed.append('REJECT')
        prompt=(f"You are ONLY the {context['role']} agent. Output a structured decision, no dialogue. "
          f"Your own allowed price range is {floor} to {ceiling}. Never go outside it. "
          'Read the last incoming offer and recent history. Use your role strategy. '
          'Do not repeat your last offer without a reason; a concession is optional, not mandatory. '
          'Seller: never exceed asking price or raise an unchanged prior offer. '
          'Buyer: open near target, then make modest progress towards a compatible counter. '
          'ACCEPT copies the incoming terms EXACTLY, including pickup, location and duration. '
          'Prefer a sensible agreement to endless counters; reject only when further progress is impossible. '
          'Allowed actions: '+', '.join(allowed)+'. Context: '+json.dumps(context))
        schema=Action.model_json_schema()
        schema['properties'].pop('message',None)
        schema['properties']['action']['enum']=allowed
        schema['$defs']['Terms']['properties']['price']={'type':'number','minimum':float(floor),'maximum':float(ceiling)}
        with INFERENCE_LOCK:
            action=None
            for attempt in range(2):
                try:
                    action=Action.model_validate_json(self.generate(prompt,schema))
                    if action.action not in allowed:raise ValueError('Use an allowed action for this turn.')
                    if action.action!='REJECT' and not action.terms:raise ValueError('Non-rejection requires terms.')
                    if action.terms and not floor<=action.terms.price<=ceiling:
                        raise ValueError(f'Your price must be between {floor} and {ceiling}.')
                    suggested=context.get('suggested_terms')
                    if action.terms and suggested and action.terms.location!=suggested['location']:
                        raise ValueError('Keep the proposed public pickup location unchanged.')
                    if action.action=='ACCEPT' and action.terms!=Terms.model_validate(last):
                        raise ValueError('ACCEPT must copy last_offer exactly; do not change any field.')
                    break
                except (ValueError,KeyError,httpx.HTTPError) as exc:
                    if attempt:raise ProviderError('Ollama returned an unavailable or invalid decision. Retry or explicitly switch to mock mode.') from exc
                    prompt+=' Correction: '+str(exc)[:220]
            # A separate public-only writing context cannot see either private price limit.
            public_context={'role':context['role'],'action':action.action,
                'terms':action.terms.model_dump(mode='json') if action.terms else None,'previous_offer':last,
                'item':{'title':context.get('listing',{}).get('title'),'type':context.get('listing',{}).get('type')},
                'conversation':[{'role':m['role'],'text':m['text'],'terms':m.get('terms')} for m in context.get('history',[])][-4:]}
            instruction=('This is the first message: greet the item owner and ask whether this offer works. Do not reference an earlier exchange.' if not context.get('history') else 'This is a reply: respond to the actual most recent offer in the conversation.')
            language_prompt=(instruction+' '+
                'Write the next friendly student-to-student message for this public negotiation. '
                'Respond naturally to the provided public conversation and briefly explain a concession or holding firm. Never pretend an earlier exchange exists when the conversation is empty. '
                'Use varied phrasing; do not repeat an earlier sentence. One or two short sentences. '
                'You know ONLY public information; do not claim any confidential price boundary. '
                'Use {price} for the CURRENT structured price; {previous_price} may acknowledge the most recent shared offer. Use {duration} for rental length, {pickup} for date/time, '
                'and {location} for the meeting place. Include {price} unless rejecting. '
                'Never write raw numbers, spelled-out numbers, money symbols, dates, days, times or confidential-limit words yourself. '
                'Do not claim a deal is confirmed: the students must approve. '
                'For ACCEPT, explicitly say the price works and the students can review. For COUNTER, ask about the new offer. '
                'Public context: '+json.dumps(public_context))
            language_schema={'type':'object','properties':{'message':{'type':'string'}},'required':['message'],'additionalProperties':False}
            if action.action!='REJECT':
                language_schema={'type':'object','properties':{'before_price':{'type':'string'},'after_price':{'type':'string'}},'required':['before_price','after_price'],'additionalProperties':False}
                language_prompt+=(' IMPORTANT OUTPUT FORMAT: write two natural sentence fragments: before_price leads into YOUR CURRENT offer; after_price continues after it. The server inserts the current price between them. Do not write any prices in these fragments. For a counter, ask whether the new price works; for acceptance, say the price works and request student review. Return only before_price and after_price in JSON.')
            for attempt in range(2):
                try:
                    reply=json.loads(self.generate(language_prompt,language_schema,120))
                    if 'before_price' in reply:
                        tail=reply['after_price'].strip()
                        message=reply['before_price'].rstrip()+' {price}'+('' if tail.startswith(('.',',','?','!',';')) else ' ')+tail
                    else:
                        message=reply['message']
                    action.message=validate_message(bind_public_facts(message,public_context['terms'],last),action.action)
                    return action
                except (ValueError,KeyError,httpx.HTTPError) as exc:
                    logging.getLogger(__name__).warning('Public-only wording blocked: %s',exc)
                    if attempt:raise ProviderError('Ollama could not produce a safe public message. Retry or explicitly switch to mock mode.') from exc
                    language_prompt+=' Correction: '+str(exc)[:200]
