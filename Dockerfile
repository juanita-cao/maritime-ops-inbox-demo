# One container for the demo: the FastAPI backend serves the API and the built frontend. The database is rebuilt at start from the
# mock emails and the recorded model answers (no network); the chat uses the key given in the host's settings.
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY . .
COPY --from=frontend /app/frontend/dist frontend/dist
ENV DATASET=mock \
    LLM_MODE=recorded \
    DEMO_NOW=2026-10-12T18:00:00+08:00 \
    E16_INCLUDE_DRAFT_PLAYBOOKS=1 \
    E16_V51_LLM_MODEL=gpt-4o-mini \
    PORT=8000
CMD python -m mockdata.load && cd backend && uvicorn src.api:app --host 0.0.0.0 --port ${PORT}
