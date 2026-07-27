FROM python:3.12-slim

WORKDIR /app

COPY Job_Helper_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY Job_Helper_agent/ ./Job_Helper_agent/

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn Job_Helper_agent.main_a2a:app --host 0.0.0.0 --port $PORT"]
