import json
from pathlib import Path

from app.core import Retriever

root = Path(__file__).resolve().parents[1]
retriever = Retriever(root / 'data/runbooks.json')
cases = json.loads((root / 'data/rag-eval.json').read_text())
results = []
for case in cases:
    sources = retriever.search(case['question'])
    top = sources[0]['id'] if sources else None
    results.append({**case, 'actual_source': top, 'passed': top == case['expected_source']})
score = sum(r['passed'] for r in results) / len(results)
reports = root / 'reports'
reports.mkdir(exist_ok=True)
(reports / 'rag-eval.json').write_text(json.dumps({'retrieval_top1_accuracy': score, 'cases': results}, indent=2))
if score < 1.0:
    raise SystemExit('RETRIEVAL GATE FAILED: inspect reports/rag-eval.json')
print(f'RETRIEVAL GATE PASSED: {len(results)}/{len(results)}')
