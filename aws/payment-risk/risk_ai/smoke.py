"""Verify the API can run both genuine framework models, locally or via port-forward."""

import argparse
import json
import urllib.request

LOW = {"amount_usd": 25, "transactions_10m": 1, "account_age_days": 1200,
       "country_mismatch": False, "failed_attempts_1h": 0, "hour": 12}
HIGH = {"amount_usd": 5000, "transactions_10m": 12, "account_age_days": 2,
        "country_mismatch": True, "failed_attempts_1h": 5, "hour": 2}


def request(url: str, payload: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None,
                                 headers={"Content-Type": "application/json"})
    # The operator supplies an HTTP(S) lab URL; smoke() validates the scheme.
    with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
        return json.load(response)


def smoke(url: str):
    if not url.startswith(("http://", "https://")):
        raise ValueError("HTTP(S) URL required")
    ready = request(url.rstrip("/") + "/readyz")
    outputs = []
    for payment, expected in ((LOW, "low_risk"), (HIGH, "review")):
        result = request(url.rstrip("/") + "/risk/predict", payment)
        assert result["bundle_version"] == ready["bundle_version"]
        assert result["synthetic_only"] is True
        assert set(result["predictions"]) == {"tensorflow", "pytorch"}
        for prediction in result["predictions"].values():
            assert prediction["label"] == expected
            assert 0 <= prediction["score"] <= 1
        outputs.append(result)
    print(json.dumps({"smoke": "passed", "engines": ["tensorflow", "pytorch"],
                      "bundle_version": ready["bundle_version"], "synthetic_only": True}))
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    smoke(parser.parse_args().url)
