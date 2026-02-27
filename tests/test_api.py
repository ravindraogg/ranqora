from fastapi.testclient import TestClient

from app.main import app
from app.models import DatasetMetadata


client = TestClient(app)


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_rank_endpoint(monkeypatch):
    def fake_search_hf(query: str, limit: int = 40):
        return [
            DatasetMetadata(id='x/1', name='dataset-one', description='nlp corpus', tags=['text']),
            DatasetMetadata(id='x/2', name='dataset-two', description='image corpus', tags=['vision']),
        ]

    monkeypatch.setattr('app.main.search_huggingface_datasets', fake_search_hf)

    response = client.post(
        '/api/v1/datasets/rank',
        json={'title': 'NLP sentiment', 'abstract': 'Need text classification data', 'top_k': 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['total_candidates'] == 2
    assert len(data['ranked']) == 1
    assert data['ranked'][0]['rank'] == 1
