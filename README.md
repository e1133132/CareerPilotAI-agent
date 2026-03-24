# CareerPilot AI (Agentic AI Career Advisor)

CareerPilot AI is a multi-agent system that helps job seekers analyze a resume, match suitable jobs, detect skill gaps, and generate a personalized study plan.

## Set up

### Option A: uv (recommended)

```sh
uv sync
uv run python main.py
```

Run API server:

```sh
uv run uvicorn api:app --host 0.0.0.0 --port 8080 --reload
```

### Option B: pip

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Run API server:

```sh
python -m uvicorn api:app --host 0.0.0.0 --port 8080 --reload
```

## Docker

Build image:

```sh
docker build -t careerpilot-ai:local .
```

Run container:

```sh
docker run --rm -p 8080:8080 --env-file .env careerpilot-ai:local
```

## What it does (agents)

- Resume Analysis Agent: extracts skills/education/experience into a structured profile + evidence.
- Job Matching Agent: ranks jobs from a local dataset (semantic matching when possible).
- Skill Gap Agent: compares profile vs job requirements to identify gaps (prioritized).
- Study Planning Agent: produces a learning roadmap with timeline + project ideas (optional **RAG** from `data/learning_resources.jsonl`).

## Data

- `data/jobs.jsonl` contains sample job descriptions you can extend.
- `data/learning_resources.jsonl` contains learning snippets for **study plan RAG** (retrieval + LLM). Add lines to expand the knowledge base. Override path with env `LEARNING_RESOURCES_PATH`. Tune `STUDY_PLAN_RAG_TOP_K` (default `5`).

## API endpoint

- `POST /api/careerpilot/run` (multipart/form-data)
  - `resume_file`: PDF file (required)
  - `target_roles`: comma separated roles (optional)

