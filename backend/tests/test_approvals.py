import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.tests.test_negotiation import start,finish

@pytest.mark.parametrize('first,second',[('student-a','student-b'),('student-b','student-a')])
def test_independent_sessions_approve_in_either_order(first,second):
    with TestClient(app) as buyer,TestClient(app) as seller,TestClient(app) as other:
        sessions={'student-a':buyer,'student-b':seller}
        for id,client in sessions.items():client.post('/demo/session',json={'student':id})
        other.post('/demo/session',json={'student':'student-c'})
        n=finish(buyer,start(buyer));path=f"/negotiations/{n['id']}"
        before=n['version']
        n=sessions[first].post(path+'/approve',json={'decision':'approve','role':'admin','status':'Confirmed'}).json()
        assert n['status']=='Awaiting approvals' and n['approvals'][first] and not n['approvals'][second]
        assert n['version']>before
        assert sessions[first].post(path+'/approve',json={'decision':'approve'}).status_code==409
        visible=sessions[second].get(path).json()
        assert visible['approvals'][first] and 'preferences' not in visible and 'minimum' not in visible['item']
        assert other.post(path+'/approve',json={'decision':'approve','student':second}).status_code==403
        assert other.get(path).status_code==403
        n=sessions[second].post(path+'/approve',json={'decision':'approve'}).json()
        assert n['status']=='Confirmed' and all(n['approvals'].values())
        for client in sessions.values():
            assert client.get(path).json()['status']=='Confirmed'
            assert n['id'] in [r['id'] for r in client.get('/negotiations').json()]
            assert client.post(path+'/approve',json={'decision':'reject'}).status_code==409
        # Persisted session and approval records are available to a fresh client.
        with TestClient(app) as refreshed:
            refreshed.cookies.update(buyer.cookies)
            assert refreshed.get(path).json()['approvals']==n['approvals']

@pytest.mark.parametrize('rejector',['student-a','student-b'])
def test_rejection_is_persisted_and_never_confirms(rejector):
    with TestClient(app) as buyer,TestClient(app) as seller:
        buyer.post('/demo/session',json={'student':'student-a'})
        seller.post('/demo/session',json={'student':'student-b'})
        clients={'student-a':buyer,'student-b':seller}
        n=finish(buyer,start(buyer));path=f"/negotiations/{n['id']}"
        other='student-b' if rejector=='student-a' else 'student-a'
        assert clients[other].post(path+'/approve',json={'decision':'approve'}).json()['status']=='Awaiting approvals'
        r=clients[rejector].post(path+'/approve',json={'decision':'reject'})
        assert r.status_code==200,r.text
        n=r.json()
        assert n['status']=='Rejected' and n['rejected_by']==rejector and n['rejected_at']
        for c in clients.values():
            assert c.post(path+'/approve',json={'decision':'approve'}).status_code==409
            assert c.get(path).json()['status']=='Rejected'
