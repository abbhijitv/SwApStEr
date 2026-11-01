"""Account-only JSON records with database-serialized, versioned mutations.

Never use demo storage helpers, identity cookies, or student profile resolution.
No schema changes or data conversion are performed by this module.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import OperationalError

from backend.models.database import Session, Record
from backend.agents import negotiation_coordinator as coordinator
from backend.services.audit import record_event

LISTING = 'account_listing'
NEGOTIATION = 'account_negotiation'
ACTIVE = ('Negotiating', 'Agreement proposed', 'Awaiting approvals')
NO_STORE = {'Cache-Control': 'private, no-store'}
LISTING_FIELDS = ('id', 'title', 'description', 'category', 'course', 'condition', 'price', 'type',
                  'rental_days', 'available_until', 'restrictions', 'version')
HOUSING_FIELDS = ('listing_type', 'neighborhood', 'lease_start', 'lease_end', 'furnished',
                  'utilities_included', 'bedrooms', 'bathrooms', 'roommate_info')
TERM_FIELDS = ('price', 'pickup', 'location', 'rental_days', 'return_date', 'transaction', 'lease_start', 'lease_end')


def fail(status, message):
    raise HTTPException(status, message, headers=NO_STORE)


def now():
    return datetime.now(timezone.utc).isoformat()


def value(record):
    return dict(deepcopy(record.data), id=record.id)


def listing_view(item, *, owner=False):
    result = {key: deepcopy(item[key]) for key in LISTING_FIELDS if key in item}
    result['seller'] = 'Marketplace seller'
    result['windows'] = [{key: window[key] for key in ('start', 'end')} for window in item.get('windows', [])]
    result['housing'] = {key: deepcopy(item['housing'][key]) for key in HOUSING_FIELDS if key in item['housing']} if item.get('housing') else None
    if owner:
        result.update(minimum=item['minimum'], seller_id=item['seller_id'], deleted=item['deleted'])
    return result


def terms_view(terms):
    return {key: deepcopy(terms[key]) for key in TERM_FIELDS if key in terms} if terms else None


def negotiation_view(item):
    def visible_terms(terms):
        result=terms_view(terms)
        if result and item['item']['type']=='Buy' and not item['item'].get('housing'):
            result.pop('rental_days',None)
            result.pop('return_date',None)
            result['transaction']='purchase'
        return result
    fields = ('id', 'listing_id', 'status', 'provider', 'turn', 'version', 'created_at', 'updated_at',
              'buyer_id', 'seller_id', 'rejected_by', 'rejected_at', 'cancelled_by', 'cancelled_at', 'reason')
    result = {key: deepcopy(item[key]) for key in fields if key in item}
    result.update(turn_limit=coordinator.turn_limit(), buyer='Buyer', seller='Seller', item=listing_view(item['item']),
                  offer=visible_terms(item.get('offer')), agreement=visible_terms(item.get('agreement')),
                  approvals={item[role+'_id']: item['approvals'].get(item[role+'_id']) is True for role in ('buyer', 'seller')},
                  messages=[{**{key: message[key] for key in ('role', 'action', 'text', 'timestamp')},
                             'terms': visible_terms(message.get('terms'))} for message in item.get('messages', [])],
                  error='The negotiation provider is unavailable or returned an invalid response. Please retry.' if item.get('error') else None)
    return result


@contextmanager
def writing():
    try:
        with Session() as db:
            if db.bind.dialect.name == 'sqlite':
                db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            yield db
            db.commit()
    except OperationalError as error:
        code = getattr(error.orig, 'sqlite_errorcode', 0)
        if (code and (code & 0xff) in (5, 6)) or getattr(error.orig, 'sqlstate', None) in {'40001', '40P01', '55P03'}:
            fail(409, 'A simultaneous update is in progress. Refresh and retry.')
        fail(503, 'Marketplace storage is temporarily unavailable.')


def row(db, kind, id, *, lock=False):
    statement = select(Record).where(Record.id == id, Record.kind == kind)
    if lock:
        statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        fail(404, 'Record not found.')
    return value(record)


def owned(item, actor):
    if item['seller_id'] != actor:
        fail(403, 'Only the listing owner can manage this listing.')


def participant(item, actor):
    if actor not in (item['buyer_id'], item['seller_id']):
        fail(404, 'Negotiation not found.')


def expected(item, version):
    if item['version'] != version:
        fail(409, 'This record changed. Refresh and retry with its current version.')


def available(item):
    if item.get('deleted'):
        fail(404, 'Listing not found.')


def compare_and_swap(db, kind, previous, changed, actor):
    expected(changed, previous['version'])
    immutable = ('seller_id', 'created_at') if kind == LISTING else ('buyer_id', 'seller_id', 'listing_id', 'listing_version', 'item', 'preferences', 'created_at')
    if any(changed.get(key) != previous.get(key) for key in immutable):
        fail(409, 'Immutable marketplace identity or private state cannot be changed.')
    changed = deepcopy(changed)
    changed.pop('id', None)
    changed['version'] = previous['version'] + 1
    changed['updated_at'] = now()
    conditions = [Record.id == previous['id'], Record.kind == kind,
                  Record.data['version'].as_integer() == previous['version']]
    if kind == LISTING:
        conditions.append(Record.data['seller_id'].as_string() == actor)
    else:
        conditions.append(or_(Record.data['buyer_id'].as_string() == actor, Record.data['seller_id'].as_string() == actor))
    result = db.execute(update(Record).where(*conditions).values(data=changed).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        fail(409, 'This record changed. Refresh and retry.')
    return dict(changed, id=previous['id'])


def insert(db, kind, data):
    record = Record(kind=kind, data=deepcopy(data))
    db.add(record)
    db.flush()
    return value(record)


def browse(*, actor=None, after=0, limit=50, include_deleted=False):
    with Session() as db:
        statement = select(Record).where(Record.kind == LISTING, Record.id > after)
        if actor:
            statement = statement.where(Record.data['seller_id'].as_string() == actor)
        if not include_deleted:
            statement = statement.where(Record.data['deleted'].as_boolean().is_(False))
        return [listing_view(value(record), owner=actor is not None) for record in db.scalars(statement.order_by(Record.id).limit(limit))]


def get_listing(id, *, actor=None):
    with Session() as db:
        item = row(db, LISTING, id)
        if actor:
            owned(item, actor)
        else:
            available(item)
        return listing_view(item, owner=actor is not None)


def create_listing(body, actor):
    data = body.model_dump(mode='json')
    if not data.get('housing') and datetime.fromisoformat(data['available_until']) <= datetime.now(timezone.utc):
        fail(422, 'Listing availability must be in the future.')
    with writing() as db:
        return listing_view(insert(db, LISTING, dict(data, seller_id=actor, seller='Marketplace seller',
                                                    version=0, deleted=False, created_at=now(), updated_at=now())), owner=True)


def change_listing(id, actor, version, body=None):
    with writing() as db:
        item = row(db, LISTING, id, lock=True)
        owned(item, actor)
        available(item)
        expected(item, version)
        active = list(db.scalars(select(Record).where(Record.kind == NEGOTIATION,
            Record.data['listing_id'].as_integer() == id, Record.data['status'].as_string().in_(ACTIVE))))
        if body is not None and active:
            fail(409, 'Close active negotiations before changing listing terms.')
        changed = deepcopy(item)
        if body is not None:
            fields = body.model_dump(mode='json', exclude={'version'})
            if not fields.get('housing') and datetime.fromisoformat(fields['available_until']) <= datetime.now(timezone.utc):
                fail(422, 'Listing availability must be in the future.')
            changed.update(fields)
        else:
            changed.update(deleted=True, deleted_at=now())
            # Owner withdrawal must not be held hostage by incoming negotiations.
            # Listing-first locking prevents new starts or approvals during this
            # transaction; completed deals remain untouched and all data is kept.
            for record in active:
                negotiation = value(record)
                if negotiation['seller_id'] != actor:
                    fail(409, 'Listing ownership is inconsistent. Withdrawal was not applied.')
                cancelled = dict(deepcopy(negotiation), status='Cancelled', cancelled_by=actor, cancelled_at=now())
                record_event(cancelled, 'offer_rejected', role='seller', action='REJECT_DEAL', result='valid', reason='student_rejected')
                compare_and_swap(db, NEGOTIATION, negotiation, cancelled, actor)
        return listing_view(compare_and_swap(db, LISTING, item, changed, actor), owner=True)


def start_negotiation(body, actor):
    preferences = body.model_dump(mode='json')
    if not body.housing and body.deadline <= datetime.now(timezone.utc):
        fail(422, 'The completion deadline must be in the future.')
    if body.housing and body.housing.desired_move_in < datetime.now(timezone.utc).date():
        fail(422, 'Move-in must not be in the past.')
    with writing() as db:
        listing = row(db, LISTING, body.listing_id, lock=True)
        available(listing)
        if listing['seller_id'] == actor:
            fail(403, 'You cannot negotiate on your own listing.')
        if bool(listing.get('housing')) != bool(body.housing):
            fail(422, 'Use preferences matching the listing type.')
        if listing['type']=='Buy' and not listing.get('housing'):
            preferences.pop('rental_days', None)
            preferences['transaction']='purchase'
        elif not listing.get('housing') and body.rental_days is None:
            fail(422, 'Rental duration is required for rental negotiations.')
        item = insert(db, NEGOTIATION, {
            'listing_id': listing['id'], 'listing_version': listing['version'], 'item': listing_view(listing),
            'buyer_id': actor, 'seller_id': listing['seller_id'], 'buyer': 'Buyer', 'seller': 'Seller',
            'preferences': preferences, 'provider': body.provider, 'status': 'Negotiating', 'messages': [],
            'offer': None, 'agreement': None, 'approvals': {actor: False, listing['seller_id']: False},
            'turn': 0, 'version': 0, 'error': None, 'created_at': now(), 'updated_at': now(),
        })
        return negotiation_view(item)


def get_negotiation(id, actor):
    with Session() as db:
        item = row(db, NEGOTIATION, id)
        participant(item, actor)
        return negotiation_view(item)


def history(actor, *, after=0, limit=50):
    with Session() as db:
        statement = select(Record).where(Record.kind == NEGOTIATION, Record.id > after,
            or_(Record.data['buyer_id'].as_string() == actor, Record.data['seller_id'].as_string() == actor))
        return [negotiation_view(value(record)) for record in db.scalars(statement.order_by(Record.id).limit(limit))]


def active_listing(db, item):
    listing = row(db, LISTING, item['listing_id'], lock=True)
    available(listing)
    if listing['seller_id'] != item['seller_id'] or listing['version'] != item['listing_version']:
        fail(409, 'Listing terms changed. Start a new negotiation.')
    return listing


def advance_negotiation(id, actor, version):
    # Never hold a database write transaction open during local/remote inference.
    with Session() as db:
        item = row(db, NEGOTIATION, id)
        participant(item, actor)
        expected(item, version)
        if item['status'] not in ('Negotiating', 'Agreement proposed'):
            fail(409, 'This negotiation is not accepting further offers.')
        listing = row(db, LISTING, item['listing_id'])
        available(listing)
        if listing['version'] != item['listing_version']:
            fail(409, 'Listing terms changed. Start a new negotiation.')
    computed = coordinator.advance(deepcopy(item), listing=listing, persist=lambda state: state,
        project=negotiation_view, listing_projection=listing_view, mock_convergence=True)
    if computed['approvals'] != item['approvals']:
        fail(409, 'Agents cannot submit human approvals.')
    allowed_statuses = {'Awaiting approvals'} if item['status'] == 'Agreement proposed' else {'Negotiating', 'Agreement proposed', 'No agreement'}
    if computed['status'] not in allowed_statuses:
        fail(409, 'Only human decisions can finalize or reject a proposal.')
    computed['version'] = item['version']
    with writing() as db:
        active_listing(db, item)  # Listing lock is always acquired before a negotiation update.
        latest = row(db, NEGOTIATION, id)
        participant(latest, actor)
        expected(latest, version)
        return negotiation_view(compare_and_swap(db, NEGOTIATION, latest, computed, actor))


def human_decision(id, actor, version, decision):
    # Initial read authorizes without exposing a listing/negotiation to outsiders.
    with Session() as db:
        snapshot = row(db, NEGOTIATION, id)
        participant(snapshot, actor)
    with writing() as db:
        listing = active_listing(db, snapshot)
        item = row(db, NEGOTIATION, id)
        participant(item, actor)
        expected(item, version)
        if item['status'] != 'Awaiting approvals' or item['approvals'].get(actor):
            fail(409, 'This proposal is closed or you have already decided.')
        if not coordinator.valid_proposal(item, listing=listing):
            fail(409, 'The proposed agreement is invalid.')
        agreement = item['agreement']
        if listing.get('housing'):
            if date.fromisoformat(agreement['lease_start']) < datetime.now(timezone.utc).date():
                fail(409, 'The proposed move-in date has passed.')
        elif coordinator.dt(agreement['pickup']) <= datetime.now(timezone.utc):
            fail(409, 'The proposed pickup time has passed.')
        changed = deepcopy(item)
        role = 'buyer' if actor == item['buyer_id'] else 'seller'
        if decision == 'reject':
            changed.update(status='Rejected', rejected_by=actor, rejected_at=now())
            record_event(changed, 'offer_rejected', role=role, action='REJECT_DEAL', result='valid', reason='student_rejected')
        else:
            changed['approvals'][actor] = True
            record_event(changed, 'approval_recorded', role=role, action='APPROVE', result='valid')
            if all(changed['approvals'].values()):
                changed['status'] = 'Confirmed'
                record_event(changed, 'agreement_finalized', role='coordinator', action='FINALIZE', result='valid', public_price=agreement['price'])
        return negotiation_view(compare_and_swap(db, NEGOTIATION, item, changed, actor))


def cancel_negotiation(id, actor, version):
    with Session() as db:
        snapshot = row(db, NEGOTIATION, id)
        participant(snapshot, actor)
    with writing() as db:
        active_listing(db, snapshot)
        item = row(db, NEGOTIATION, id)
        participant(item, actor)
        expected(item, version)
        if item['status'] not in ACTIVE:
            fail(409, 'A closed negotiation cannot be cancelled.')
        changed = dict(deepcopy(item), status='Cancelled', cancelled_by=actor, cancelled_at=now())
        record_event(changed, 'offer_rejected', role='buyer' if actor == item['buyer_id'] else 'seller',
                     action='REJECT_DEAL', result='valid', reason='student_rejected')
        return negotiation_view(compare_and_swap(db, NEGOTIATION, item, changed, actor))
