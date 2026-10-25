from decimal import Decimal
from datetime import datetime
from backend.models.schemas import Action
class MockProvider:
    def decide(self, c):
        own, last = c['private'], c.get('last_offer')
        n = c['own_turn']
        buyer = c['role']=='buyer'
        low = Decimal(own.get('minimum', own.get('target', '0')))
        high = Decimal(own.get('maximum', own.get('price', '0')))
        if buyer and c.get('listing',{}).get('price') is not None:
            high=min(high,Decimal(c['listing']['price']));low=min(low,high)
        if last:
            p=Decimal(last['price'])
            acceptable = p<=min(high,low+Decimal(n)*Decimal('5')) if buyer else p>=low
            if acceptable:
                return Action(action='ACCEPT',terms=last,message=('Thanks for meeting me halfway. {price} works for me; let’s send the terms for our students to review.' if n else 'That sounds fair. I’m happy with {price}; our students can review the details.'))
        if buyer:
            p=min(high,low+Decimal(n)*Decimal('5'))
            if last: p=min(p,Decimal(last['price']))
        else:
            p=max(low,high-Decimal(n+1)*Decimal('10'))
        purchase=c.get('listing',{}).get('type')=='Buy'
        terms=dict(c['suggested_terms'],price=str(p))
        message=('Hey! Would {price} work for {duration}? I can meet at {location} on {pickup}.' if not last else
                 ('Thanks for considering it. Could we meet at {price}? The suggested pickup works for me.' if buyer else
                  'Thanks for the offer! Could you do {price} for {duration}? I can meet at {location}.'))
        if purchase:message=message.replace('for {duration}', 'for this item')
        return Action(action='COUNTER' if last else 'OFFER',terms=terms,message=message)
