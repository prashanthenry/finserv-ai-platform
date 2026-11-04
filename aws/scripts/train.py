"""Train, evaluate held-out examples, and export an auditable JSON model."""
import hashlib
import json
import os
from pathlib import Path

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import f1_score, classification_report
from sklearn.naive_bayes import MultinomialNB

from app.core import tokens

root = Path(__file__).resolve().parents[1]
data_bytes = (root / 'data/incidents.json').read_bytes()
data = json.loads(data_bytes)
vectorizer = CountVectorizer(analyzer=tokens)
x_train = vectorizer.fit_transform([r['text'] for r in data['train']])
model = MultinomialNB().fit(x_train, [r['label'] for r in data['train']])
predictions = model.predict(vectorizer.transform([r['text'] for r in data['test']]))
labels = [r['label'] for r in data['test']]
score = f1_score(labels, predictions, average='macro')
artifact = {'dataset_sha256': hashlib.sha256(data_bytes).hexdigest(),
            'algorithm': 'MultinomialNB', 'vocabulary': vectorizer.vocabulary_,
            'classes': model.classes_.tolist(), 'class_log_prior': model.class_log_prior_.tolist(),
            'feature_log_prob': model.feature_log_prob_.tolist()}
version = hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()[:12]
artifact['model_version'] = version
reports = root / 'reports'
reports.mkdir(exist_ok=True)
report = {'macro_f1': score, 'threshold': 0.80, 'dataset_sha256': artifact['dataset_sha256'],
          'classification_report': classification_report(labels, predictions, output_dict=True),
          'train_rows': len(data['train']), 'test_rows': len(data['test'])}
(reports / 'model-eval.json').write_text(json.dumps(report, indent=2))
if score < 0.80:
    raise SystemExit(f'MODEL GATE FAILED: macro_f1={score:.4f}')
artifact_dir = root / 'artifacts'
artifact_dir.mkdir(exist_ok=True)
(artifact_dir / 'model.json').write_text(json.dumps(artifact, indent=2))
if os.getenv('MLFLOW_TRACKING_URI'):
    import mlflow
    mlflow.set_experiment('payment-incident-classifier')
    with mlflow.start_run():
        mlflow.log_params({'algorithm': 'MultinomialNB', 'dataset_sha256': artifact['dataset_sha256']})
        mlflow.log_metric('macro_f1', score)
        mlflow.log_artifact(str(artifact_dir / 'model.json'))
        mlflow.log_artifact(str(reports / 'model-eval.json'))
print(f'MODEL GATE PASSED: macro_f1={score:.4f}, version={version}')
