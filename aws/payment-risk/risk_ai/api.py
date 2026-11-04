"""Independent payment-risk API: the existing copilot API stays separate."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Response

from risk_ai.features import ROOT, Payment
from risk_ai.serving import RiskService


def create_app(artifacts: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.risk = RiskService(artifacts or Path(os.environ.get("RISK_ARTIFACT_DIR", ROOT / "artifacts")))
        # Load and warm both engines before accepting requests.
        app.state.risk.predict(Payment(amount_usd=50, transactions_10m=1, account_age_days=500,
                                      country_mismatch=False, failed_attempts_1h=0, hour=12))
        yield

    app = FastAPI(title="Synthetic Payment Risk — TensorFlow and PyTorch", lifespan=lifespan)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        # Swagger UI uses CDN scripts and inline initialization.
        if request.url.path != "/docs":
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        return {"status": "ready", "bundle_version": app.state.risk.version}

    @app.get("/version")
    def version():
        return {"bundle_version": app.state.risk.version, "synthetic_only": True,
                "tensorflow": app.state.risk.manifest["tensorflow_version"],
                "pytorch": app.state.risk.manifest["pytorch_version"]}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response('risk_model_loaded{engine="tensorflow"} 1\nrisk_model_loaded{engine="pytorch"} 1\n',
                        media_type="text/plain; version=0.0.4")

    @app.post("/risk/predict")
    def predict(payment: Payment, engine: Literal["both", "tensorflow", "pytorch"] = Query(default="both")):
        return app.state.risk.predict(payment, engine)

    return app


app = create_app()
