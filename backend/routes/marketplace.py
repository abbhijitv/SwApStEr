"""Staged account API. Demo cookies never authorize these routes."""
import os

from fastapi import APIRouter, Depends, Query, Response
from backend.auth import AccountUser, authenticated_user
from backend.models.database import engine
from backend.models.marketplace_schemas import AccountListing, ListingUpdate, NegotiationStart, ExpectedVersion, HumanDecision
from backend.services import account_marketplace as service


def enabled(response: Response):
    response.headers.update(service.NO_STORE)
    if os.getenv('ENABLE_ACCOUNT_MARKETPLACE', 'false').lower() != 'true':
        service.fail(404, 'Account marketplace is not enabled.')
    if engine.dialect.name == 'sqlite' and (engine.url.database in (None, '', ':memory:') or engine.url.query.get('mode') == 'memory'):
        service.fail(503, 'Account marketplace requires a file-backed database.')


router = APIRouter(prefix='/marketplace', tags=['Account marketplace'], dependencies=[Depends(enabled)])


@router.get('/listings')
def listings(after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return service.browse(after=after, limit=limit)


@router.get('/listings/mine')
def own_listings(user: AccountUser = Depends(authenticated_user), after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), include_deleted: bool = False):
    return service.browse(actor=user.id, after=after, limit=limit, include_deleted=include_deleted)


@router.post('/listings', status_code=201)
def create_listing(body: AccountListing, user: AccountUser = Depends(authenticated_user)):
    return service.create_listing(body, user.id)


@router.get('/listings/{id}/manage')
def manage_listing(id: int, user: AccountUser = Depends(authenticated_user)):
    return service.get_listing(id, actor=user.id)


@router.get('/listings/{id}')
def public_listing(id: int):
    return service.get_listing(id)


@router.put('/listings/{id}')
def edit_listing(id: int, body: ListingUpdate, user: AccountUser = Depends(authenticated_user)):
    return service.change_listing(id, user.id, body.version, body)


@router.delete('/listings/{id}', status_code=204)
def delete_listing(id: int, version: int = Query(..., ge=0), user: AccountUser = Depends(authenticated_user)):
    service.change_listing(id, user.id, version)
    return Response(status_code=204, headers=service.NO_STORE)


@router.post('/negotiations', status_code=201)
def start(body: NegotiationStart, user: AccountUser = Depends(authenticated_user)):
    return service.start_negotiation(body, user.id)


@router.get('/negotiations')
def history(user: AccountUser = Depends(authenticated_user), after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return service.history(user.id, after=after, limit=limit)


@router.get('/negotiations/{id}')
def retrieve(id: int, user: AccountUser = Depends(authenticated_user)):
    return service.get_negotiation(id, user.id)


@router.post('/negotiations/{id}/advance')
def advance(id: int, body: ExpectedVersion, user: AccountUser = Depends(authenticated_user)):
    return service.advance_negotiation(id, user.id, body.version)


@router.post('/negotiations/{id}/approve')
def approve(id: int, body: HumanDecision, user: AccountUser = Depends(authenticated_user)):
    return service.human_decision(id, user.id, body.version, body.decision)


@router.post('/negotiations/{id}/cancel')
def cancel(id: int, body: ExpectedVersion, user: AccountUser = Depends(authenticated_user)):
    return service.cancel_negotiation(id, user.id, body.version)
