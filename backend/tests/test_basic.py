from fastapi.testclient import TestClient
from backend.main import app
client=TestClient(app)
def test_health(): assert client.get('/health').json()['status']=='ok'
def test_listings():
    items=client.get('/listings').json()
    assert len(items)>=5
    assert 'minimum' not in items[0]
    assert client.get('/listings/999999').status_code==404
