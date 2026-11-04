"""Small, inspectable retrieval and JSON model inference; no pickle loading."""
import json
import math
import re
from collections import Counter
from pathlib import Path

STOP = {'the', 'and', 'for', 'with', 'what', 'how', 'does', 'when', 'can', 'are', 'our', 'from', 'this', 'that', 'should'}


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r'[a-z][a-z0-9_]+', text.lower()) if t not in STOP]


def redact(text: str) -> str:
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
    text = re.sub(r'\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b', '[EMAIL]', text)
    return re.sub(r'\b\d{8,19}\b', '[ACCOUNT]', text)


class Retriever:
    """Lexical TF-IDF cosine retrieval. Deliberately not a vector database."""
    def __init__(self, path: Path):
        self.docs = json.loads(path.read_text())
        self.counts = [Counter(tokens(d['title'] + ' ' + d['text'])) for d in self.docs]
        vocabulary = set().union(*(set(c) for c in self.counts))
        self.idf = {t: math.log((1 + len(self.docs)) / (1 + sum(t in c for c in self.counts))) + 1 for t in vocabulary}

    def search(self, question: str, limit: int = 2) -> list[dict]:
        q = Counter(tokens(question))
        ranked = []
        for doc, counts in zip(self.docs, self.counts):
            numerator = sum(n * counts[t] * self.idf.get(t, 0) ** 2 for t, n in q.items())
            norm_q = math.sqrt(sum((n * self.idf.get(t, 0)) ** 2 for t, n in q.items()))
            norm_d = math.sqrt(sum((n * self.idf[t]) ** 2 for t, n in counts.items()))
            score = numerator / (norm_q * norm_d) if norm_q and norm_d else 0
            if score >= 0.10:
                ranked.append({**doc, 'score': round(score, 4)})
        return sorted(ranked, key=lambda d: d['score'], reverse=True)[:limit]


def classify(text: str, model: dict) -> dict:
    counts = Counter(tokens(text))
    scores = list(model['class_log_prior'])
    known = False
    for word, count in counts.items():
        index = model['vocabulary'].get(word)
        if index is not None:
            known = True
            for i in range(len(scores)):
                scores[i] += count * model['feature_log_prob'][i][index]
    if not known:
        return {'category': 'unknown', 'confidence': 0.0}
    probabilities = [math.exp(s - max(scores)) for s in scores]
    total = sum(probabilities)
    index = max(range(len(scores)), key=lambda i: scores[i])
    return {'category': model['classes'][index], 'confidence': round(probabilities[index] / total, 4)}
