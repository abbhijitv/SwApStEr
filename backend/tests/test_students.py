"""Dynamic ownership, authorization, and non-destructive legacy compatibility."""
import json
import os
import sqlite3
import subprocess
import sys
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.store import all_records, seed
from backend.tests.test_negotiation import prefs, start, finish


def profile(c, name='New student'):
    r=c.post('/students', json={'display_name':name, 'university':'Arizona State', 'course_or_major':'Engineering'})
    assert r.status_code==201, r.text
    return r.json()

def select(c, id):
    r=c.post('/demo/session',json={'student':id})
    assert r.status_code==200,r.text
    return r.json()

def listing(c):
    original=c.get('/listings').json()[0]
    body={k:v for k,v in original.items() if k not in ('id','seller','seller_id','icon')}
    body.update(title='Dynamic academic kit '+uuid4().hex[:8],minimum='20',seller_id='student-b',seller='Forged owner')
    r=c.post('/listings',json=body)
    assert r.status_code==201,r.text
    return r.json()

def test_create_list_and_validate_students():
    with TestClient(app) as c:
        a=profile(c,'  New student  ');b=profile(c)
        assert a['display_name']=='New student'
        assert a['id']!=b['id'] and a['id'] not in ('student-a','student-b','student-c')
        assert a['created_at'] and a['university']=='Arizona State'
        assert c.get('/students/'+a['id']).json()==a
        assert a in c.get('/students').json()
        for name in ['', '   ', 'a'*81, 'bad\x00name']:
            assert c.post('/students',json={'display_name':name}).status_code==422
        assert c.post('/students',json={'display_name':'Valid','university':{}}).status_code==422
        assert c.post('/students',json={'display_name':'Valid','id':'student-a'}).status_code==422
        assert c.get('/students/nonexistent').status_code==404

def test_switch_profile_cookie_and_ownership():
    with TestClient(app) as c:
        p=profile(c)
        assert select(c,p['id'])['profile']['display_name']==p['display_name']
        token=c.cookies.get('campus_session')
        assert c.get('/demo/session').json()['student']==p['id']
        l=listing(c)
        assert l['seller_id']==p['id'] and l['seller']==p['display_name'] and 'minimum' not in l
        assert l in c.get('/listings').json()
        body=prefs(c);body['listing_id']=l['id']
        assert c.post('/negotiations',json=body).status_code==403
        assert c.post('/demo/session',json={'student':'missing-id'}).status_code==404
        assert c.get('/demo/session').json()['student']==p['id']
        # A separate client (or restarted browser session) resolves the persisted token.
        with TestClient(app) as another:
            another.cookies.set('campus_session',token)
            assert another.get('/demo/session').json()['student']==p['id']
            assert another.get('/listings/'+str(l['id'])).json()['seller_id']==p['id']

def test_arbitrary_pairs_constraints_history_and_approvals(monkeypatch):
    from backend.agents.mock_provider import MockProvider
    captured=[]
    original=MockProvider.decide
    def spy(self,ctx): captured.append(ctx);return original(self,ctx)
    monkeypatch.setattr(MockProvider,'decide',spy)
    with TestClient(app) as c:
        seller=profile(c,'Arbitrary seller');buyer=profile(c,'Arbitrary buyer');third=profile(c,'Unrelated student')
        select(c,seller['id']);l=listing(c)
        select(c,buyer['id']);body=prefs(c);body['listing_id']=l['id']
        n=finish(c,start(c,body))
        assert n['status']=='Awaiting approvals'
        assert n['buyer_id']==buyer['id'] and n['seller_id']==seller['id']
        assert n['buyer']==buyer['display_name'] and n['seller']==seller['display_name']
        assert set(n['approvals'])=={buyer['id'],seller['id']}
        assert set(ctx['principal']['id'] for ctx in captured)=={buyer['id'],seller['id']}
        for ctx in captured:
            if ctx['role']=='buyer': assert 'minimum' not in json.dumps(ctx)
            else: assert 'maximum' not in json.dumps(ctx) and ctx['private']['minimum']=='20'
        for actor in (buyer,seller):
            select(c,actor['id'])
            saved=c.get(f"/negotiations/{n['id']}").json()
            assert 'preferences' not in saved and 'minimum' not in saved['item']
            assert n['id'] in [x['id'] for x in c.get('/negotiations').json()]
        select(c,third['id'])
        assert n['id'] not in [x['id'] for x in c.get('/negotiations').json()]
        for suffix,method,payload in [('', 'get', None),('/approve','post',{'decision':'approve','role':'seller','student':seller['id']}),('/advance','post',{'version':n['version']}),('/mock','post',{})]:
            response=c.get(f"/negotiations/{n['id']}"+suffix) if method=='get' else c.post(f"/negotiations/{n['id']}"+suffix,json=payload)
            assert response.status_code==403,response.text
        select(c,buyer['id'])
        assert c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()['status']=='Awaiting approvals'
        select(c,seller['id'])
        confirmed=c.post(f"/negotiations/{n['id']}/approve",json={'decision':'approve'}).json()
        assert confirmed['status']=='Confirmed' and all(confirmed['approvals'].values())
        # The same seller can buy from the former buyer in a different transaction.
        select(c,buyer['id']);other=listing(c)
        select(c,seller['id']);body['listing_id']=other['id']
        reverse=finish(c,start(c,body))
        assert reverse['status']=='Awaiting approvals' and reverse['buyer_id']==seller['id']

def test_oumar_independent_demo_and_idempotent_seeds():
    with TestClient(app) as c:
        before={kind:len(all_records(kind)) for kind in ('student','listing','negotiation')}
        for _ in range(3):seed()
        assert before=={kind:len(all_records(kind)) for kind in before}
        names={p['id']:p['display_name'] for p in c.get('/students').json()}
        assert names['student-a']=='Abbhijit' and names['student-b']=='Shorya Moses' and names['student-c']=='Oumar'
        select(c,'student-c');n=finish(c,start(c))
        assert n['buyer']=='Oumar' and n['seller']=='Shorya Moses' and n['status']=='Awaiting approvals'
        assert n['buyer_id']=='student-c'


def test_legacy_migration_preserves_records_and_restart(tmp_path):
    path=tmp_path/'legacy.db'
    legacy=[
      (1,'student',{'identity':'student-a','name':'Alex Rivera','custom':'preserve'}),
      (2,'student',{'identity':'student-b','name':'Maya Chen'}),
      (3,'listing',{'seller_id':'student-b','seller':'Maya Chen','title':'Keep this custom listing','minimum':'23','custom':{'important':True}}),
      (4,'negotiation',{'buyer_id':'student-a','seller_id':'student-b','buyer':'Alex Rivera','seller':'Maya Chen','listing_id':3,'item':{'title':'Keep this custom listing'},'preferences':{'maximum':'27'},'status':'Confirmed','approvals':{'student-a':True,'student-b':True},'messages':[{'role':'buyer','text':'Existing public message'}]}),
      (5,'session',{'student':'student-a','token':'persisted-demo-token'})]
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE records (id INTEGER PRIMARY KEY,kind VARCHAR,data JSON)')
        db.executemany('INSERT INTO records VALUES (?,?,?)',[(id,kind,json.dumps(data)) for id,kind,data in legacy])
    env=dict(os.environ,DATABASE_URL='sqlite:///'+str(path),APP_ENV='development')
    command=[sys.executable,'-c',"from backend.main import app; from backend.services.store import seed; seed()"]
    subprocess.run(command,env=env,check=True,capture_output=True,text=True)
    with sqlite3.connect(path) as db:
        after={id:(kind,json.loads(data)) for id,kind,data in db.execute('SELECT * FROM records')}
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    for id,kind,data in legacy:
        if kind!='student':assert after[id]==(kind,data)
    assert after[1][1]['identity']=='student-a' and after[1][1]['display_name']=='Abbhijit'
    assert after[1][1]['name']=='Alex Rivera' and after[1][1]['custom']=='preserve'
    assert after[2][1]['display_name']=='Shorya Moses'
    assert sum(kind=='student' for kind,data in after.values())==3
    assert list((tmp_path/'backups').glob('*.db'))
    subprocess.run(command,env=env,check=True,capture_output=True,text=True)
    with sqlite3.connect(path) as db:
        assert after=={id:(kind,json.loads(data)) for id,kind,data in db.execute('SELECT * FROM records')}
    # A fresh interpreter resolves old session cookies and participant names after restart.
    check="""
from fastapi.testclient import TestClient
from backend.main import app
c=TestClient(app);c.cookies.set('campus_session','persisted-demo-token')
assert c.get('/demo/session').json()['profile']['display_name']=='Abbhijit'
n=c.get('/negotiations/4').json()
assert n['buyer']=='Abbhijit' and n['seller']=='Shorya Moses'
assert n['approvals']=={'student-a':True,'student-b':True}
assert 'preferences' not in n
"""
    subprocess.run([sys.executable,'-c',check],env=env,check=True,capture_output=True,text=True)
