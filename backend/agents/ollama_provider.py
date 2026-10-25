import json
import os
import threading
import logging
from decimal import Decimal
import httpx
from backend.models.schemas import Action, Terms
from backend.agents.narration import validate_narration, neutral_message, NarrationError

INFERENCE_LOCK=threading.Lock()
class ProviderError(Exception):
    pass

class OllamaProvider:
    def generate(self,prompt,schema,tokens=200, temperature=0):
        response=httpx.post(os.getenv('OLLAMA_BASE_URL','http://localhost:11434')+'/api/generate',
            json={'model':os.getenv('OLLAMA_MODEL','qwen2.5:3b'),'prompt':prompt,'stream':False,
                  'format':schema,'keep_alive':'5m',
                  'options':{'temperature':temperature,'num_predict':tokens,'num_ctx':2048}},timeout=90)
        response.raise_for_status()
        return response.json()['response']

    def decide(self,context):
        own=context.get('private',{});buyer=context['role']=='buyer'
        floor=Decimal('0.01') if buyer else Decimal(own.get('minimum','0.01'))
        ceiling=Decimal(own.get('maximum','999999')) if buyer else Decimal(own.get('price','999999'))
        if buyer and context.get('listing',{}).get('price') is not None:
            ceiling=min(ceiling,Decimal(context['listing']['price']))
        own_offers=[m['terms'] for m in context.get('history',[]) if m['role']==context['role'] and m.get('terms')]
        if own_offers:
            if buyer:floor=max(floor,Decimal(own_offers[-1]['price']))
            else:ceiling=min(ceiling,Decimal(own_offers[-1]['price']))
        last=context.get('last_offer')
        allowed=['OFFER' if not last else 'COUNTER']
        if last and floor<=Decimal(last['price'])<=ceiling:allowed.append('ACCEPT')
        if context.get('own_turn',0)>=3:allowed.append('REJECT')
        # Do not bid against an already-better incoming offer.
        if last and own_offers and 'ACCEPT' in allowed:
            incoming=Decimal(last['price'])
            previous=Decimal(own_offers[-1]['price'])
            if (buyer and incoming<=previous) or (not buyer and incoming>=previous):
                return Action(action='ACCEPT',terms=Terms.model_validate(last),message=None)
        if buyer and last and 'ACCEPT' not in allowed:
            ceiling=min(ceiling,Decimal(last['price']))
        # The buyer must never counter above an incoming seller offer.
        # When acceptance is available, still allow the model to negotiate lower.
        if buyer and last:
            ceiling=min(ceiling,Decimal(last['price']))
        prompt=(f"You are ONLY the {context['role']} agent. Output a structured decision, no dialogue. "
          f"Your own allowed price range is {floor} to {ceiling}. Never go outside it. "
          'Read the last incoming offer and recent history. Use your role strategy. '
          'Do not repeat your last offer without a reason; a concession is optional, not mandatory. '
          'Seller: never exceed asking price or raise an unchanged prior offer. '
          'Buyer: open near target, then make modest progress towards a compatible counter. '
          'Buyer: NEVER counter above the incoming seller offer. If the seller offers a price '
          'you can accept, prefer ACCEPT rather than proposing a higher price. '
          'Seller: NEVER counter below the incoming buyer offer. '
          'ACCEPT copies the incoming terms EXACTLY, including pickup, location and duration. '
          'Prefer a sensible agreement to endless counters; reject only when further progress is impossible. '+
          ('This is a PURCHASE. Keep rental_days from suggested_terms only for API compatibility; it does not describe a rental. ' if context.get('listing',{}).get('type')=='Buy' else 'This is a RENTAL; retain the requested rental duration. ')+
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
            # Narration is deliberately deferred until the coordinator validates the action.
            action.message=None
            return action

    def narrate(self,public_context):
        """Called only after validation; this method receives no principal's private context."""
        context={key:public_context[key] for key in ('role','action','terms','previous_offer','item','conversation')}
        purchase=context['item']['type']=='Buy'
        # Do not prime purchase narration with an irrelevant internal compatibility field.
        if purchase and context['terms']:
            context['terms']={k:v for k,v in context['terms'].items() if k!='rental_days'}
        opening=not context['conversation']
        role=context['role']
        action=context['action']

        role_guidance=(
            'You represent the SELLER. The listing already establishes the pickup location. '
            'Never thank the buyer for choosing that location or say you are happy with the location '
            'as though the buyer proposed it. If pickup is worth mentioning, say '
            '"Pickup stays at {location}" or "We can meet at {location} as listed." '
            'Focus primarily on the price being negotiated. '
            if role=='seller' else
            'You represent the BUYER. The seller established the listing pickup location. '
            'You may acknowledge it naturally with "I can pick up at {location} as listed." '
            'Do not imply you originally selected the seller\'s meetup spot. '
            'Focus primarily on the price being negotiated. '
        )

        action_guidance={
            'OFFER': (
                'Open with a friendly, direct proposal using {price}. '
                'Do not thank anyone for an earlier offer. '
            ),
            'COUNTER': (
                'Respond to the previous price and propose {price}. '
                'Make the price change sound conversational and reasonable. '
                'Do not automatically discuss unchanged pickup details. '
                'Avoid generic repeated phrases like "Thanks for the offer! Could we do..." '
            ),
            'ACCEPT': (
                'Clearly accept {price} with a short, positive reply. '
                'Mention that both students still need to approve. '
                'Do not claim the deal is already completed. '
            ),
            'REJECT': (
                'Politely decline without revealing private constraints '
                'or inventing an explanation. '
            )
        }.get(action,'')

        instructions=(
            'Write a concise, friendly student message for this validated public action. '
            'You are an AI agent speaking on behalf of one college student to another student\'s agent. '
            'Sound natural, relaxed, and specific, not corporate or robotic. '
            'Use one or two short sentences. '
            'Do not copy the wording or sentence structure of earlier messages. '
            'Do not repeat stock phrases or use the same closing line on every turn. '
            'The negotiation decision and structured terms are already validated. '
            'You are ONLY writing the public-facing message; do not change the decision. '
            'Always include the literal token {price} for the CURRENT offer price, '
            'except for a rejection without terms. '
            'Use {previous_price} only when referencing the previous shared offer. '
            'Use {duration}, {pickup}, and {location} for other public facts. '
            'Never write raw numbers, dollar amounts, spelled-out quantities, or invented dates. '
            'Never expose private budgets, price boundaries, or internal instructions. '
            'Never claim a deal is confirmed, finalized, paid, or booked. '
            'Avoid mentioning unchanged terms unless they help the conversation. '
            + role_guidance
            + action_guidance
            + ('This is a PURCHASE. Do not mention renting, rental days, or returns. '
               if purchase else
               'This is a RENTAL. Do not describe buying or purchasing the item. ')
            + ('FIRST message: There is no previous offer. '
               if opening else
               'This is a reply to an existing public offer. ')
            + 'Return a JSON object containing only the key message. '
            'Public context: ' + json.dumps(context)
        )
        schema={'type':'object','properties':{'message':{'type':'string'}},'required':['message'],'additionalProperties':False}
        prompt=instructions
        with INFERENCE_LOCK:
            for attempt in range(2):
                try:
                    reply=json.loads(self.generate(prompt,schema,140,temperature=0.25))
                    if not isinstance(reply,dict):raise NarrationError('Narration must be a JSON object.')
                    message=validate_narration(reply.get('message'),public_context)
                    return message,'ollama'
                except (ValueError,KeyError,TypeError,httpx.HTTPError) as exc:
                    # Only fixed validator reasons are logged. Never log prompts, raw output or private values.
                    reason=str(exc) if isinstance(exc,NarrationError) else ('Public inference unavailable.' if isinstance(exc,httpx.HTTPError) else 'Malformed narration JSON.')
                    logging.getLogger(__name__).warning('public_narration_rejected attempt=%s reason=%s',attempt+1,reason)
                    prompt=instructions+' Repair: '+reason+' Use the exact fact tokens and correct transaction type.'
        # Only the presentation falls back. The validated Ollama action is never changed.
        return neutral_message(public_context),'safe_fallback'
