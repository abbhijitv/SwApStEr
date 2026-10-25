"""Exercise a full live API negotiation. Run from root with servers running."""
import argparse, json
from datetime import datetime, timedelta
from decimal import Decimal
import httpx
parser=argparse.ArgumentParser()
parser.add_argument('--provider',choices=['mock','ollama'],default='mock')
args=parser.parse_args()
with httpx.Client(base_url='http://localhost:8000',timeout=200) as c:
    def post(path,body):
        r=c.post(path,json=body);r.raise_for_status();return r.json()
    post('/demo/session',{'student':'student-a'})
    l=c.get('/listings').json()[0]
    start=datetime.fromisoformat(l['windows'][0]['start'])
    n=post('/negotiations',{'listing_id':l['id'],'target':'15','maximum':'25','rental_days':3,
        'deadline':(start+timedelta(days=2)).isoformat(),'windows':l['windows'],
        'location':'Hayden Library','provider':args.provider})
    for i in range(9):
        if n['status'] not in ('Negotiating','Agreement proposed'): break
        n=post(f"/negotiations/{n['id']}/advance",{'version':n['version']})
        if n.get('error'): raise RuntimeError(n['error'])
        print(json.dumps({'turn':n['turn'],'provider':n['provider'],'event':n['messages'][-1]},indent=2),flush=True)
    assert n['status']=='Awaiting approvals',n
    assert Decimal('20')<=Decimal(n['agreement']['price'])<=Decimal('25')
    n=post(f"/negotiations/{n['id']}/approve",{'decision':'approve'})
    assert n['status']=='Awaiting approvals'
    post('/demo/session',{'student':'student-b'})
    n=post(f"/negotiations/{n['id']}/approve",{'decision':'approve'})
    assert n['status']=='Confirmed'
    print(json.dumps({'id':n['id'],'provider':n['provider'],'status':n['status'],'agreement':n['agreement']},indent=2))
