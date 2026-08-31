# Cloud Run image for the MedSight A2A server (A2UI-enabled).
# Gemini Enterprise renders A2UI only for agents registered via the A2A path,
# so the agent must be served as a self-hosted A2A endpoint — this image does
# exactly that.
#
# Build & deploy (from the repo root):
#   gcloud run deploy medsight-a2ui \
#     --source medsight --region us-central1 \
#     --set-env-vars A2A_PUBLIC_URL=https://<your-cloud-run-url>
#
# Cloud Run injects $PORT; uvicorn binds to it.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The package must be importable as `medsight`, so copy it into a subdir.
COPY . ./medsight/

ENV A2A_HOST=0.0.0.0
EXPOSE 8080

# Bind to Cloud Run's $PORT (defaults to 8080 locally).
CMD ["sh", "-c", "uvicorn medsight.a2a_server:app --host 0.0.0.0 --port ${PORT:-8080}"]
