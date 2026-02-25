# Research-agent

Autonomous multi-step research-paper agentic workflow using Grok as the central reasoner.

This version is **live-only** (no mock reasoning fallback).  
If Grok API fails, the run returns a clear error instead of synthetic output.

Core capabilities:

- Iterative loop: `plan -> decompose -> tool select -> analyze -> refine/replan -> summarize`
- Grok-driven planning, reflection, and synthesis
- Query-intent-aware orchestration profile (`multi_paper_overview` vs `focused_analysis`)
- Hybrid retrieval (`semantic + keyword`) over structured paper sections
- Context memory with compression and citation tracking
- Ambiguity resilience via automatic replanning triggers
- Compact trace visualization: each step shows summary stats/top hits/replan signal, not full chunk text

## Project Structure

```text
research_agent/
  agent.py         # Main autonomous loop
  grok.py          # Live Grok integration (strict JSON contracts)
  tools.py         # Tool execution (hybrid search/timeline/citation graph)
  retrieval.py     # Hybrid retrieval engine
  memory.py        # Context management and compression
  dataset.py       # Paper dataset loading/chunking
  pdf_ingest.py    # PDF -> structured dataset conversion
  server.py        # Web API + frontend static server
  config.py        # Environment configuration
data/
  real_papers.json # Real paper dataset generated from PDFs
  sample_papers.json # Small sample dataset for local tests
frontend/
  index.html       # Web console
  app.js           # Frontend logic
  styles.css       # Visual design
scripts/
  pdf_to_dataset.py
tests/
  test_retrieval.py
  test_agent.py
```

## Quick Start

1. Configure `.env`:

```bash
GROK_API_KEY=your_key
GROK_BASE_URL=https://api.x.ai/v1/chat/completions
GROK_MODEL=grok-4-1-fast-reasoning
```

2. Run the agent:

```bash
python -m research_agent.cli \
  --query "What causes citation hallucination in review agents?" \
  --data data/real_papers.json \
  --json
```

3. Optional full trace (large):

```bash
python -m research_agent.cli \
  --query "..." \
  --data data/real_papers.json \
  --json \
  --full-trace
```

4. Run tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

5. Run web frontend:

```bash
python -m research_agent.server --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787`.
The CLI and web server automatically load variables from `.env` if present.

## Realtime Run Status

The web UI uses async run APIs for live progress:

- `POST /api/run`: enqueue a run, returns `{run_id, status}`
- `GET /api/runs/{run_id}`: poll status/progress/compact trace/result
- `POST /api/run-sync`: optional blocking run for scripts

Progress stages include `planning`, `planned`, `step_started`, `step_finished`, `replanned`, `summarizing`, `completed`, and `failed`.

## What the Agent Does

For each query, the agent:

1. Asks Grok to create a multi-step plan with tool assignments.
2. Executes retrieval tools against structured paper sections (`abstract/methodology/findings/limitations`).
3. Stores evidence and decisions in compressed context memory.
4. Uses Grok reflection to detect ambiguity:
   - low evidence coverage
   - conflicting stances across sources
5. Automatically inserts replanning steps when ambiguity is detected.
6. Produces a grounded final synthesis with citations and risks.

## Real PDF Workflow

Convert a folder of PDFs into agent-ready dataset JSON:

```bash
python scripts/pdf_to_dataset.py \
  --pdf-dir data/pdfs \
  --out data/real_papers.json
```

Then run the agent on real dataset:

```bash
python -m research_agent.cli \
  --query "What are the dominant failure modes in citation-grounded review agents?" \
  --data data/real_papers.json \
  --json
```

Optional metadata CSV (`filename,paper_id,title,year,language,venue,authors,keywords`) can improve record quality:

```bash
python scripts/pdf_to_dataset.py \
  --pdf-dir data/pdfs \
  --out data/real_papers.json \
  --metadata-csv data/paper_metadata.csv
```

Notes:
- PDF extraction tries `pypdf` first, then `pdftotext`.
- Install `pypdf` if needed: `pip install pypdf`.
- For the UI/API, `execution_trace` is compact by default. Full raw observations are only returned when `include_full_trace=true`.
- PDF ingest generates collision-resistant `paper_id` values and auto-resolves duplicates.
