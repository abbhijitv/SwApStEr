"""Bounded Phase 1 verification. Uses genuine Ollama and a disposable SQLite DB."""
import json
import os
from pathlib import Path
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from datetime import datetime,timedelta

# Set the DB before any backend imports. Existing student data is never touched.
_temporary=tempfile.TemporaryDirectory(prefix='campusswap-phase1-live-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_temporary.name)/'smoke.db')
os.environ['APP_ENV']='development'
os.environ['ENABLE_JUDGE_MODE']='false'
from fastapi.testclient import TestClient
from backend.main import app
from backend.agents.ollama_provider import OllamaProvider
import httpx

# Instrument request count only: model responses are never supplied or modified by this script.
_original=OllamaProvider.generate
_counts={'decision':0,'narration':0,'network_calls':0}
def counted(self,prompt,schema,tokens=200,temperature=0):
    if _counts['network_calls']>=18:raise httpx.TimeoutException('Phase 1 inference budget reached')
    _counts['network_calls']+=1
    _counts['narration' if temperature else 'decision']+=1
    return _original(self,prompt,schema,tokens,temperature)
OllamaProvider.generate=counted

output=Path('artifacts/phase1-ollama.json');output.parent.mkdir(exist_ok=True)
report={'rental':None,'purchase_opening':None,'counts':_counts}

def check(response):
    response.raise_for_status();return response.json()
def advance(client,n):
    n=check(client.post(f"/negotiations/{n['id']}/advance",json={'version':n['version']}))
    if n.get('error'):raise RuntimeError(n['error'])
    return n
try:
    with TestClient(app) as buyer,TestClient(app) as seller:
        check(buyer.post('/demo/session',json={'student':'student-a'}))
        check(seller.post('/demo/session',json={'student':'student-b'}))
        listings=check(buyer.get('/listings'))
        def begin(item,target,maximum):
            start=datetime.fromisoformat(item['windows'][0]['start'])
            return check(buyer.post('/negotiations',json={'listing_id':item['id'],'target':target,'maximum':maximum,
                'rental_days':item['rental_days'],'deadline':(start+timedelta(days=2)).isoformat(),
                'windows':item['windows'],'location':'Hayden Library','provider':'ollama'}))
        item=next(x for x in listings if x['title']=='TI-84 Plus CE Graphing Calculator')
        n=begin(item,'15','25')
        for _ in range(9):
            if n['status'] not in ('Negotiating','Agreement proposed'):break
            before=n['turn'];n=advance(buyer,n);report['rental']=n
            if n['turn']!=before:print(json.dumps(n['messages'][-1]),flush=True)
        assert n['provider']=='ollama' and n['status']=='Awaiting approvals',n['status']
        assert n['agreement']['return_date'] and not any(n['approvals'].values())
        n=check(buyer.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}))
        assert n['status']=='Awaiting approvals'
        n=check(seller.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}))
        assert n['status']=='Confirmed'
        report['rental']=n
        print('RENTAL CONFIRMED AFTER TWO INDEPENDENT APPROVALS',flush=True)
        # One genuine purchase opening verifies type/first-turn wording without a second long loop.
        item=next(x for x in listings if x['type']=='Buy')
        purchase=advance(buyer,begin(item,'16','35'))
        report['purchase_opening']=purchase
        assert purchase['turn']==1 and purchase['messages'][0]['action']=='OFFER'
        text=purchase['messages'][0]['text'].lower()
        assert not any(word in text for word in ('rent','return','duration','your offer','counteroffer'))
        assert purchase['agreement'] is None
        print('PURCHASE OPENING:',purchase['messages'][0]['text'],flush=True)
        report['result']='passed'
except Exception as exc:
    report['result']='failed';report['error']=str(exc);raise
finally:
    output.write_text(json.dumps(report,indent=2))
    print('Evidence:',output,'Requests:',_counts,flush=True)
    _temporary.cleanup()
