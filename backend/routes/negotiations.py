import os, secrets, threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from backend.models.schemas import Preferences
from backend.services.students import student_by_id
from backend.services.store import get, save, all_records, public_listing
from backend.agents.negotiation_coordinator import advance, public
router=APIRouter()
LOCKS=defaultdict(threading.Lock)

def demo_only():
    if os.getenv('APP_ENV','development')!='development': raise HTTPException(403,'Demo identity and judge features are disabled')

def identity(request:Request):
    demo_only()
    token=request.cookies.get('campus_session')
    session=next((s for s in all_records('session') if secrets.compare_digest(s['token'],token or '')),None)
    if not session: raise HTTPException(401,'Select a demo student first')
    if not student_by_id(session['student']): raise HTTPException(401,'Selected student no longer exists')
    return session['student']
class Student(BaseModel):
    student: str
@router.post('/demo/session')
def switch(body:Student,response:Response):
    demo_only()
    profile=student_by_id(body.student)
    if not profile: raise HTTPException(404,'Student not found')
    token=secrets.token_urlsafe(32)
    save('session',{'token':token,'student':body.student})
    response.set_cookie('campus_session',token,httponly=True,samesite='lax',secure=False,max_age=30*24*60*60)
    return {'student':body.student,'profile':profile}
@router.get('/demo/session')
def who(student=Depends(identity)): return {'student':student,'profile':student_by_id(student)}

def authorized(id,student):
    n=get('negotiation',id)
    if not n: raise HTTPException(404,'Negotiation not found')
    if student not in (n['buyer_id'],n['seller_id']): raise HTTPException(403,'Not a participant')
    return n
@router.post('/negotiations',status_code=201)
def start(body:Preferences,student=Depends(identity)):
    l=get('listing',body.listing_id)
    if not l: raise HTTPException(404,'Listing not found')
    if student==l['seller_id']: raise HTTPException(403,'You cannot negotiate on your own listing')
    if body.deadline<=datetime.now(timezone.utc): raise HTTPException(422,'Academic deadline must be in the future')
    n=save('negotiation',{'listing_id':l['id'],'item':public_listing(l),'buyer':student_by_id(student)['display_name'],'seller':student_by_id(l['seller_id'])['display_name'],
      'buyer_id':student,'seller_id':l['seller_id'],'preferences':body.model_dump(mode='json'),
      'provider':body.provider,'status':'Negotiating','messages':[],'offer':None,'agreement':None,
      'approvals':{student:False,l['seller_id']:False},'turn':0,'version':0,'error':None,
      'created_at':datetime.now(timezone.utc).isoformat()})
    return public(n)
@router.get('/negotiations')
def history(student=Depends(identity)):
    return [public(n) for n in all_records('negotiation') if student in (n['buyer_id'],n['seller_id'])]
@router.get('/negotiations/{id}')
def retrieve(id:int,student=Depends(identity)): return public(authorized(id,student))
class Advance(BaseModel): version:int
@router.post('/negotiations/{id}/advance')
def next_turn(id:int,body:Advance,student=Depends(identity)):
    lock=LOCKS[id]
    if not lock.acquire(blocking=False): raise HTTPException(409,'An agent is already thinking')
    try:
        n=authorized(id,student)
        if n['version']!=body.version: raise HTTPException(409,'This turn has already advanced')
        return public(advance(n))
    finally: lock.release()
class Approval(BaseModel): decision:Literal['approve','reject']
@router.post('/negotiations/{id}/approve')
def approve(id:int,body:Approval,student=Depends(identity)):
    with LOCKS[id]:
        n=authorized(id,student)
        if n['status']!='Awaiting approvals': raise HTTPException(409,'This deal is not awaiting approvals')
        if n['approvals'][student]: raise HTTPException(409,'You already approved this deal')
        if body.decision=='reject':
            n.update(status='Rejected',rejected_by=student,rejected_at=datetime.now(timezone.utc).isoformat())
        else:
            n['approvals'][student]=True
            if all(n['approvals'].get(id,False) for id in (n['buyer_id'],n['seller_id'])): n['status']='Confirmed'
        n['version']+=1
        return public(save('negotiation',n,id))
@router.post('/negotiations/{id}/mock')
def switch_mock(id:int,student=Depends(identity)):
    with LOCKS[id]:
        n=authorized(id,student)
        if n['status']!='Negotiating': raise HTTPException(409,'Negotiation is closed')
        n.update(provider='mock',error=None)
        return public(save('negotiation',n,id))
@router.get('/demo/judge/{id}')
def judge(id:int,request:Request,student=Depends(identity)):
    demo_only()
    if request.client.host not in ('127.0.0.1','::1','testclient'): raise HTTPException(403,'Judge mode is loopback only')
    if os.getenv('ENABLE_JUDGE_MODE','false').lower()!='true': raise HTTPException(403,'Judge mode disabled')
    n=authorized(id,student)
    return {'buyer_private':n['preferences'],'seller_private':get('listing',n['listing_id']),'negotiation':public(n)}
