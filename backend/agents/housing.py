"""Deterministic housing constraints; no private facts enter public explanations."""
from datetime import date, timedelta
from decimal import Decimal

def compatible(p, l):
    h, wanted = l['housing'], p['housing']
    start, end = date.fromisoformat(wanted['desired_move_in']), date.fromisoformat(wanted['desired_move_out'])
    available = date.fromisoformat(h['lease_start'])
    chosen = max(start, available)
    if chosen > start + timedelta(days=wanted['move_in_flex_days']) or end > date.fromisoformat(h['lease_end']) or chosen >= end:
        return None
    if wanted.get('preferred_location') and wanted['preferred_location'].casefold() not in h['neighborhood'].casefold(): return None
    for key in ('furnished', 'utilities_included'):
        if wanted.get(key) is not None and wanted[key] != h[key]: return None
    return {'transaction':'housing','price':p['target'],'location':h['neighborhood'],'lease_start':chosen.isoformat(),'lease_end':end.isoformat()}

def valid(t, p, l, role=None):
    try:
        expected = compatible(p, l)
        if not expected or t.get('transaction') != 'housing' or t.get('pickup') is not None or t.get('rental_days') is not None: return False
        start, end = date.fromisoformat(t['lease_start']), date.fromisoformat(t['lease_end'])
        desired = date.fromisoformat(p['housing']['desired_move_in'])
        flex = timedelta(days=p['housing']['move_in_flex_days'])
        if not (date.fromisoformat(l['housing']['lease_start']) <= start < end <= date.fromisoformat(l['housing']['lease_end'])): return False
        if not desired-flex <= start <= desired+flex or end != date.fromisoformat(p['housing']['desired_move_out']) or t['location'] != expected['location']: return False
        price = Decimal(t['price'])
        return price.is_finite() and price > 0 and (role == 'seller' or price <= Decimal(p['maximum'])) and (role == 'buyer' or Decimal(l['minimum']) <= price <= Decimal(l['price']))
    except (KeyError, ValueError, TypeError, ArithmeticError): return False
