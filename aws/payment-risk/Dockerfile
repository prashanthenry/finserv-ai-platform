# CPU deep-learning wheels need glibc. Authenticate first: docker login dhi.io
# Build with --platform linux/amd64, including on Apple Silicon.
FROM dhi.io/python:3.12.16-dev AS dependencies
USER 0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/risk
RUN python3 -m venv --without-pip /venv
COPY requirements-linux.txt .
# Install into the target venv using the builder's pip. Do not copy pip or its
# bundled dependencies/SBOM into the inference image.
RUN python3 -m pip --python /venv install --no-cache-dir -r requirements-linux.txt

FROM dependencies AS trainer
COPY requirements-dev.txt .
RUN python3 -m pip --python /venv install --no-cache-dir -r requirements-dev.txt
ENV PATH="/venv/bin:$PATH"
COPY risk_ai ./risk_ai
RUN chown -R 10001:10001 /opt/risk
USER 10001:10001
RUN python -m risk_ai.generate && python -m risk_ai.train

FROM dhi.io/python@sha256:76f58066fa95a3ce3b4eb74026b8dda9bfeb3ea14780a211ab634e30bbcbcab7 AS runtime
ENV PATH="/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /opt/risk
COPY --from=dependencies /venv /venv
RUN ["/venv/bin/python", "-c", "import importlib.util; assert importlib.util.find_spec('pip') is None, 'pip must stay in the builder/trainer stages'"]
COPY --chown=10001:10001 risk_ai ./risk_ai
USER 10001:10001
ENTRYPOINT []
EXPOSE 8000
CMD ["/venv/bin/python", "-m", "uvicorn", "risk_ai.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

# CI packages the exact model pair tested by the quality job; no retraining here.
FROM runtime AS ci
COPY --chown=10001:10001 artifacts ./artifacts
RUN ["/venv/bin/python", "-c", "from risk_ai.serving import RiskService; from risk_ai.features import ROOT; RiskService(ROOT / 'artifacts')"]

# The default local build trains inside Linux, including on Intel Macs.
FROM runtime AS standalone
COPY --from=trainer --chown=10001:10001 /opt/risk/artifacts ./artifacts
RUN ["/venv/bin/python", "-c", "from risk_ai.serving import RiskService; from risk_ai.features import ROOT; RiskService(ROOT / 'artifacts')"]
