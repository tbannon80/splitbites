import uvicorn
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json() == {'status': 'healthy', 'service': 'splitbites-backend'}
    print('Health endpoint test passed.')

def test_generate_plan():
    response = client.post('/api/meal-plans/generate', json={'household_id': 1, 'target_date': '2026-09-07'})
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'generated'
    assert 'Monday' in data['plan']
    print('Meal plan generation test passed.')

if __name__ == '__main__':
    test_health()
    test_generate_plan()
    print('All core API tests passed successfully.')
