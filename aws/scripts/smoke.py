"""Cloud releases require a real inference call; offline answers cannot pass."""
import argparse
import json
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8000')
parser.add_argument('--require-live', action='store_true')
args = parser.parse_args()


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(args.url + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as response:  # trusted operator-supplied URL
        return json.load(response)


assert request('/readyz')['status'] == 'ready'
prediction = request('/predict', {'description': 'payment timeout downstream bank latency'})
assert prediction['category'] == 'timeout', prediction
answer = request('/ask', {'question': 'How should we investigate payment API timeout latency?'})
assert any(s['id'] == 'PAY-001' for s in answer['sources']), answer
assert '[PAY-001]' in answer['answer'], 'Missing expected citation'
if args.require_live:
    assert answer['live_inference'] is True, 'Cloud deployment returned offline output'
    assert answer['provider'] == 'bedrock'
print(json.dumps({'smoke': 'passed', 'live_inference': answer['live_inference'],
                  'provider': answer['provider'], 'model_version': prediction['model_version']}))
