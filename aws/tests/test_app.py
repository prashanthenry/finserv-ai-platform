from pathlib import Path
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import Retriever, classify, redact
from app.main import app
from app.providers import generate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'offline')
    with TestClient(app) as c:
        yield c


def test_offline_is_explicit(client):
    answer = client.post('/ask', json={'question': 'payment API timeout latency'}).json()
    assert answer['live_inference'] is False
    assert answer['answer'].startswith('OFFLINE EXTRACT:')
    assert answer['sources'][0]['id'] == 'PAY-001'


def test_unknown_question_refuses(client):
    response = client.post('/ask', json={'question': 'banana bread recipe'}).json()
    assert response['sources'] == []
    assert 'not have enough information' in response['answer']


def test_provider_error_is_not_mocked(client, monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'bedrock')
    with patch('app.main.generate', side_effect=RuntimeError('secret error details')):
        response = client.post('/ask', json={'question': 'payment timeout'})
    assert response.status_code == 502
    assert 'secret error' not in response.text


def test_redacts_before_provider(client):
    with patch('app.main.generate', return_value={'answer': 'test', 'input_tokens': 0,
                                                'output_tokens': 0, 'live_inference': False}) as mocked:
        client.post('/ask', json={'question': 'timeout for john@example.com SSN 123-45-6789 account 123456789012'})
    question = mocked.call_args.args[0]
    assert 'john@example.com' not in question
    assert '123-45-6789' not in question
    assert '123456789012' not in question


def test_request_size_validation(client):
    assert client.post('/ask', json={'question': 'a' * 2001}).status_code == 422


def test_model_holdout_inference(client):
    assert client.post('/predict', json={'description': 'token expired unauthorized'}).json()['category'] == 'authentication'
    assert client.post('/predict', json={'description': 'memory pressure oomkilled'}).json()['category'] == 'capacity'


def test_model_unknown_words():
    model = json.loads((ROOT / 'artifacts/model.json').read_text())
    assert classify('zebras waltzing', model)['category'] == 'unknown'


def test_metrics_and_version(client):
    assert 'copilot_requests_total' in client.get('/metrics').text
    assert client.get('/version').json()['prompt_version'] == 'runbook-v1'


def test_redaction():
    assert redact('abc 123-45-6789') == 'abc [SSN]'


def test_bad_provider_rejected(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'typo')
    with pytest.raises(ValueError):
        generate('question', [])


def test_retrieval_does_not_add_unrelated_docs():
    assert Retriever(ROOT / 'data/runbooks.json').search('banana bread recipe') == []


def test_other_cloud_rejected(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'azure')
    with pytest.raises(ValueError):
        generate('question', [])
