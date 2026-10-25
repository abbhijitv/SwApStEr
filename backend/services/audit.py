"""Allowlisted, internal audit events persisted with the negotiation's state."""
from datetime import datetime, timezone
from decimal import Decimal

EVENTS = {
    'offer_proposed', 'offer_accepted', 'offer_rejected',
    'constraint_violation', 'approval_recorded', 'agreement_finalized',
}
REASONS = {
    'pickup_incompatible', 'rental_duration_incompatible', 'item_unavailable',
    'invalid_agent_terms', 'provider_error', 'unsafe_narration', 'agent_declined',
    'turn_limit', 'stalled', 'unauthorized_participant', 'duplicate_approval',
    'invalid_state', 'invalid_proposal', 'student_rejected', 'stale_version',
}
PRICE_EVENTS = {'offer_proposed', 'offer_accepted', 'agreement_finalized'}


def record_event(negotiation, category, *, role, action, result, reason=None,
                 public_price=None, turn=None):
    """No free-form context/text is accepted. Invalid/private proposals never log a price.

    Callers save the containing negotiation once, atomically with the state change.
    Existing records need no migration and public API projections omit audit_events.
    """
    if category not in EVENTS or role not in {'buyer', 'seller', 'coordinator'}:
        raise ValueError('Unsupported audit category or role')
    if action not in {'OFFER', 'COUNTER', 'ACCEPT', 'REJECT', 'DECIDE',
                      'APPROVE', 'REJECT_DEAL', 'FINALIZE'}:
        raise ValueError('Unsupported audit action')
    if result not in {'valid', 'rejected', 'failed'} or (reason is not None and reason not in REASONS):
        raise ValueError('Unsupported audit validation result or reason')
    if type(negotiation['id']) is not int or negotiation['id'] <= 0:
        raise ValueError('Invalid audit negotiation ID')
    event_turn = negotiation.get('turn') if turn is None else turn
    if type(event_turn) is not int or not 0 <= event_turn <= 8:
        event_turn = None
    if public_price is not None:
        if category not in PRICE_EVENTS or result != 'valid':
            raise ValueError('Only validated public offers may have an audit price')
        price = Decimal(str(public_price))
        if not price.is_finite() or price <= 0:
            raise ValueError('Invalid public audit price')
        public_price = str(price)
    event = {
        'category': category,
        'negotiation_id': negotiation['id'],
        'turn': event_turn,
        'agent_role': role,
        'action_type': action,
        'public_price': public_price,
        'validation_result': result,
        'rejection_reason': reason,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    negotiation.setdefault('audit_events', []).append(event)
    return event
