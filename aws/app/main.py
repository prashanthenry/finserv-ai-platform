import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from botocore.exceptions import ClientError

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field

from app.core import Retriever, classify, redact
from app.providers import generate

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
REQUESTS = Counter('copilot_requests_total', 'Requests', ['route', 'result'])
LATENCY = Histogram('copilot_inference_seconds', 'Answer generation latency')
TOKENS = Counter('copilot_tokens_total', 'Provider usage', ['direction'])


@asynccontextmanager
async def lifespan(app):
    # Missing/corrupt model prevents readiness rather than silently serving an old model.
    app.state.model = json.loads((ROOT / 'artifacts/model.json').read_text())
    app.state.retriever = Retriever(ROOT / 'data/runbooks.json')
    yield


app = FastAPI(title='Payment Operations AI Copilot', lifespan=lifespan)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class Incident(BaseModel):
    description: str = Field(min_length=3, max_length=2000)


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.get('/readyz')
def ready():
    return {'status': 'ready', 'model_version': app.state.model['model_version']}


@app.get('/version')
def version():
    return {'commit': os.getenv('APP_VERSION', 'local'), 'provider': os.getenv('AI_PROVIDER', 'offline'),
            'model_version': app.state.model['model_version'], 'prompt_version': 'runbook-v1'}


@app.get('/metrics')
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post('/predict')
def predict(body: Incident):
    result = classify(redact(body.description), app.state.model)
    REQUESTS.labels('predict', 'success').inc()
    return {**result, 'model_version': app.state.model['model_version']}


@app.post('/ask')
def ask(body: Question):
    question = redact(body.question)
    sources = app.state.retriever.search(question)
    start = time.monotonic()
    try:
        response = generate(question, sources)
        except Exception as exc:
        if isinstance(exc, ClientError):
            error = exc.response.get('Error', {})
            log.error(
                'inference_failed operation=%s aws_code=%s message=%s',
                exc.operation_name,
                error.get('Code'),
                error.get('Message'),
            )
        else:
            log.error('inference_failed error_type=%s', type(exc).__name__)

        REQUESTS.labels('ask', 'error').inc()
        raise HTTPException(
            502, 'AI provider request failed; check model access and workload identity'
        ) from None
    # except Exception as exc:
    #     # Log only error class, never provider response bodies or user prompts.
    #     log.error('inference_failed error_type=%s', type(exc).__name__)
    #     REQUESTS.labels('ask', 'error').inc()
    #     raise HTTPException(502, 'AI provider request failed; check model access and workload identity') from None
    finally:
        LATENCY.observe(time.monotonic() - start)
    REQUESTS.labels('ask', 'success').inc()
    TOKENS.labels('input').inc(response['input_tokens'])
    TOKENS.labels('output').inc(response['output_tokens'])
    return {**response, 'sources': [{'id': d['id'], 'score': d['score']} for d in sources],
            'provider': os.getenv('AI_PROVIDER', 'offline'), 'prompt_version': 'runbook-v1'}
