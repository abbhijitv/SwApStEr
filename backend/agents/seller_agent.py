def context(listing, public_listing, messages, last_offer, suggested_terms):
    private={k:listing[k] for k in ['minimum','price','windows','rental_days','available_until','restrictions','type']}
    if listing.get('housing'): private['housing']=listing['housing']
    return {'role':'seller','strategy':'Anchor at or below asking price. Make measured concessions in response to the buyer, or hold once if justified. Never raise your previous unchanged offer. Accept compatible terms when further bargaining adds little value.','private':private,'listing':public_listing,'history':messages[-4:],
            'last_offer':last_offer,'suggested_terms':suggested_terms,
            'own_turn':sum(m['role']=='seller' for m in messages)}
