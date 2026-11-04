FROM python:3.12-alpine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && addgroup -g 10001 appuser \
    && adduser -D -u 10001 -G appuser appuser
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 data/runbooks.json ./data/runbooks.json
COPY --chown=10001:10001 artifacts/model.json ./artifacts/model.json
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
