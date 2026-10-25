def context(preferences, listing, messages, last_offer, suggested_terms):
    return {'role':'buyer','strategy':'Start near the target. Respond to the last public counter. Make a measured increase only when useful; never bid against yourself. Accept a good compatible offer.','private':preferences,'listing':listing,'history':messages[-4:],
            'last_offer':last_offer,'suggested_terms':suggested_terms,
            'own_turn':sum(m['role']=='buyer' for m in messages)}
