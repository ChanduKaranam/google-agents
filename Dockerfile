FROM python:3.12-slim
WORKDIR /app

COPY faculty_agents_dispatcher/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY faculty_agents_dispatcher/ ./faculty_agents_dispatcher/

ENV PORT=8080

# Without this google-genai talks to the Gemini Developer API and wants an API
# key: the container boots green and fails on the first model call. `.env` is
# not in the image and nothing calls load_dotenv, so bake it here.
ENV GOOGLE_GENAI_USE_VERTEXAI=1

# Draw A2UI cards. Set only here — the Agent Engine deployment must never have
# it, because that registration cannot render cards and would show the
# professor raw JSON.
ENV FACULTY_AGENT_A2UI=1

EXPOSE 8080
CMD ["sh", "-c", "uvicorn faculty_agents_dispatcher.main_a2a:app --host 0.0.0.0 --port $PORT"]
