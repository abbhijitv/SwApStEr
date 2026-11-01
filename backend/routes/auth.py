from fastapi import APIRouter, Depends, Response

from backend.auth import AccountUser, authenticated_user

router = APIRouter(prefix='/auth', tags=['Authentication'])


@router.get('/me', response_model=AccountUser)
def me(response: Response, user: AccountUser = Depends(authenticated_user)):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Authorization'
    return user
