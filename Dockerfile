FROM python:3.12-slim

WORKDIR /app

COPY Job_Helper_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY Job_Helper_agent/ ./Job_Helper_agent/

ENV PORT=8080
# ADK's own cli_deploy.py bakes this. Without it google-genai talks to the
# Gemini Developer API and needs an API key, so the container boots green and
# then fails on the first model call. .env is excluded from the image and
# nothing calls load_dotenv, so it has to be baked here.
ENV GOOGLE_GENAI_USE_VERTEXAI=1
EXPOSE 8080

CMD ["sh", "-c", "uvicorn Job_Helper_agent.main_a2a:app --host 0.0.0.0 --port $PORT"]
