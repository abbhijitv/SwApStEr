"""Public-only language: validated facts replace tokens after model generation."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

class NarrationError(ValueError):
    pass

TOKENS={'price','previous_price','duration','pickup','location'}
PRIVATE_WORDS=re.compile(r'\b(maximum|minimum|reservation|private|secret|ceiling|floor|prompt|instructions|limit)\b',re.I)

NUMBER_WORDS={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}

def bind_public_facts(message,terms,previous=None):
    """Normalize equivalent model formatting; contradictory figures still fail closed."""
    if not isinstance(message,str) or not terms:return message
    message=re.sub(r'^(?:REPLY|OFFER|COUNTER|ACCEPT|REJECT|BUYER(?: AGENT)?|SELLER(?: AGENT)?)\s*:\s*','',message.strip(),flags=re.I)
    if '{previous_price}' in message and not previous:raise NarrationError('There is no earlier public offer to quote.')
    from decimal import Decimal
    def money(match):
        value=match.group(1).replace(',','')
        if Decimal(value)==Decimal(terms['price']):return '{price}'
        if previous and Decimal(value)==Decimal(previous['price']):return '{previous_price}'
        raise NarrationError('Quote only the current price or the most recent shared price. Use fact tokens.')
    message=re.sub(r'\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)',money,message)
    message=re.sub(r'\b(\d+(?:\.\d+)?)\s+dollars?\b',money,message,flags=re.I)
    def duration(match):
        words=match.group(1).lower().replace('-',' ').split()
        amount=int(words[0]) if words[0].isdigit() else sum(NUMBER_WORDS.get(word,-1000) for word in words)
        if amount!=terms.get('rental_days',0):raise NarrationError('Rental duration must equal structured terms; use {duration}.')
        return '{duration}'
    numbers='|'.join(NUMBER_WORDS)
    message=re.sub(r'\b(\d+|(?:'+numbers+r')(?:[ -](?:'+numbers+r'))?)\s*[- ]\s*days?\b',duration,message,flags=re.I)
    pickup=datetime.fromisoformat(terms['pickup'].replace('Z','+00:00')).astimezone(ZoneInfo('America/Phoenix'))
    day=pickup.strftime('%A');hour=pickup.strftime('%-I');period=pickup.strftime('%p')
    minute=pickup.strftime('%M');time=hour+(r'(?::00)?' if minute=='00' else ':'+minute)+r'\s*'+period
    message=re.sub(r'\b'+day+r'\s+(?:at\s+)?'+time+r'\b','{pickup}',message,flags=re.I)
    message=re.sub(r'\b'+time+r'\b','{pickup}',message,flags=re.I)
    message=re.sub(r'\b'+day+r'\b','{pickup}',message,flags=re.I)
    message=re.sub(r'\{pickup\}\s+(?:at|on)\s+\{pickup\}','{pickup}',message)
    message=re.sub(re.escape(terms['location']),'{location}',message,flags=re.I)
    return message

def validate_message(message,action):
    if not isinstance(message,str) or not 12<=len(message)<=400:
        raise NarrationError('Write one or two concise conversational sentences.')
    tokens=set(re.findall(r'\{([^{}]+)\}',message))
    if tokens-TOKENS or message.count('{')!=message.count('}'):
        raise NarrationError('Use only {price}, {previous_price}, {duration}, {pickup}, {location} fact tokens.')
    stripped=re.sub(r'\{(?:price|previous_price|duration|pickup|location)\}','',message)
    if re.search(r'[\d$£€{}]',stripped) or PRIVATE_WORDS.search(stripped):
        raise NarrationError('Do not write raw numbers, money, or confidential-limit language. Use fact tokens.')
    # Reject spelled-out numeric claims too; facts must come from the structured terms.
    if re.search(r'\b(dollars?|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',stripped,re.I):
        raise NarrationError('Put prices, durations, and pickup dates only in the corresponding fact tokens.')
    if action!='REJECT' and 'price' not in tokens:
        raise NarrationError('Include {price} so the public message matches this offer.')
    if re.search(r'\b(confirmed|finalized|booked|paid)\b',stripped,re.I):
        raise NarrationError('Acceptance proposes terms for student review; it does not confirm a deal.')
    return message.strip()

def render_message(message,action,terms,previous=None):
    text=validate_message(bind_public_facts(message,terms,previous),action)
    if not terms:
        if re.search(r'\{',text):raise NarrationError('A rejection without terms cannot quote terms.')
        return text
    pickup=datetime.fromisoformat(terms['pickup'].replace('Z','+00:00')).astimezone(ZoneInfo('America/Phoenix'))
    from decimal import Decimal
    price=Decimal(terms['price'])
    facts={'price':f'${price:,.2f}'.removesuffix('.00'),
           'duration':f"{terms.get('rental_days',0)} days",'pickup':pickup.strftime('%A at %-I:%M %p'),
           'location':terms['location']}
    if previous:facts['previous_price']=f"${Decimal(previous['price']):,.2f}".removesuffix('.00')
    for key,value in facts.items():text=text.replace('{'+key+'}',value)
    return text


def validate_narration(message,context):
    """Validate language against only the already-approved public facts and conversation."""
    text=bind_public_facts(message,context['terms'],context.get('previous_offer'))
    text=validate_message(text,context['action'])
    purchase=context['item']['type']=='Buy'
    if not purchase and re.search(
        r'(?:\{price\}|\{previous_price\})\s*(?:/|per\s+)(?:day|night|week|month)\b',
        text,re.I
    ):
        raise NarrationError('Rental price is the total for the rental, not a daily or weekly rate.')
    if context['role']=='seller' and re.search(
        r'\b(?:i|we)\s+(?:can|will|would|could|am|are|plan to|intend to)\s+(?:pick\s*up|collect)\b',
        text,re.I
    ):
        raise NarrationError('Seller provides the listed meetup spot; seller must not claim to pick up the item.')
    if purchase and (re.search(r'\b(rent|rental|renting|return|duration|days?|per.book|per.day)\b',text,re.I) or '{duration}' in text):
        raise NarrationError('Purchase wording cannot describe rental duration, a return date, or a rate.')
    if not purchase and re.search(r'\b(buy|buying|purchase|per.book)\b',text,re.I):
        raise NarrationError('Rental wording cannot describe a purchase.')
    if not context['conversation'] and re.search(r'\b(your (?:counter)?offer|counteroffer|thanks for (?:the|your) offer|same (?:duration|pickup)|meeting me halfway)\b',text,re.I):
        raise NarrationError('Opening message cannot acknowledge a previous offer or agreement.')
    if context['action']=='ACCEPT' and re.search(r'\b(could|would) you\b',text,re.I):
        raise NarrationError('Acceptance should accept the outstanding offer, not propose a new counter.')
    if context['action'] in ('OFFER','COUNTER') and re.search(r'\b(that works|i accept|we accept|we agree|agreed)\b',text,re.I):
        raise NarrationError('An offer or counter must not claim that an agreement has been accepted.')
    if context['action']=='OFFER' and re.search(r'\b(?:priced|listed|costs|asking price)\s+(?:at\s+|is\s+|for\s+)?\{price\}',text,re.I):
        raise NarrationError('Opening message must propose the current price, not claim it is the listed price.')
    # Reject copied wording, while leaving the validated action and all terms untouched.
    rendered=render_message(text,context['action'],context['terms'],context.get('previous_offer'))
    def canonical(value):
        value=re.sub(r'^(?:REPLY|OFFER|COUNTER|ACCEPT|REJECT)\s*:\s*','',value.strip(),flags=re.I)
        return ' '.join(value.casefold().split())
    if any(canonical(rendered)==canonical(m['text']) for m in context['conversation']):
        raise NarrationError('Do not repeat an earlier public message verbatim. Express the current action in your own words.')
    return text


def neutral_message(context):
    """Presentation-only fallback for an action which the coordinator has already validated."""
    action=context['action']
    if action=='REJECT':return 'Thanks for discussing it. I do not think these terms will work.'
    if action=='ACCEPT':return '{price} works for me. Let’s send the proposal to our students for approval.'
    if action=='COUNTER':return 'Thanks for the offer. Could we meet at {price}?'
    if context['item']['type']=='Buy':return 'Would you consider {price} for this item?'
    return 'Would {price} work for {duration}?'
