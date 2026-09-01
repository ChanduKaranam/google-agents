# Cloud Run image for the Clinical Case Simulator.
#
# Serves the A2A interface: JSON-RPC at / and the agent card at
# /.well-known/agent-card.json. That is the surface Gemini Enterprise
# registers — a raw `adk api_server` endpoint is not.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

RUN adduser --disabled-password --gecos "" --uid 1001 appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY clinical_simulator ./clinical_simulator

USER appuser
EXPOSE 8080

# A2A_PUBLIC_URL is set by deploy.sh once Cloud Run has assigned a URL; the
# agent card must advertise the public address, not the container's.
CMD exec uvicorn clinical_simulator.a2a_app:app --host 0.0.0.0 --port ${PORT}
