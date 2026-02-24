# Research-agent

Autonomous multi-step research-paper agentic workflow using Grok as the central reasoner.

This prototype is built for the `research paper` track and includes:

- Iterative loop: `plan -> decompose -> tool select -> analyze -> refine/replan -> summarize`
- Grok-driven planning, reflection, and synthesis (with offline mock mode fallback)
- Hybrid retrieval (`semantic + keyword`) over structured mock paper excerpts
- Context memory with compression and citation tracking
- Ambiguity resilience via automatic replanning triggers

## Project Structure

```text
research_agent/
  agent.py         # Main autonomous loop
  grok.py          # Grok integration (live + mock)
  tools.py         # Tool execution (hybrid search/timeline/citation graph)
  retrieval.py     # Hybrid retrieval engine
  memory.py        # Context management and compression
  dataset.py       # Mock paper loading/chunking
  pdf_ingest.py    # PDF -> structured dataset conversion
  server.py        # Web API + frontend static server
  config.py        # Environment configuration
data/
  mock_papers.json # High-quality mock research paper dataset
frontend/
  index.html       # Web console
  app.js           # Frontend logic
  styles.css       # Visual design
scripts/
  generate_mock_papers.py
  pdf_to_dataset.py
tests/
  test_retrieval.py
  test_agent.py
```

## Quick Start

1. Run the agent in mock Grok mode:

```bash
python -m research_agent.cli \
  --query "How reliable is hybrid retrieval for multilingual literature reviews?"
```

2. Get full JSON trace:

```bash
python -m research_agent.cli \
  --query "What causes citation hallucination in review agents?" \
  --json
```

3. Run tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

4. Run web frontend:

```bash
python -m research_agent.server --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787`.

## Optional Live Grok Mode

Set environment variables:

```bash
export GROK_API_KEY="your_key"
export GROK_BASE_URL="https://api.x.ai/v1/chat/completions"
export GROK_MODEL="grok-2-latest"
export GROK_MOCK=false
```

Then run the same CLI command. If API configuration is missing, the system falls back to deterministic mock reasoning.

The CLI and web server automatically load variables from `.env` if present.

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

## Mock Dataset Characteristics

`data/mock_papers.json` includes 10 papers with:

- multilingual entries (`en`, `zh`, `es`)
- conflicting claims (support/challenge/mixed stances)
- citation links for graph inspection
- realistic sections: abstract, methodology, findings, limitations
- edge cases: benchmark leakage, PDF parsing noise, context compression failures

## Real PDF Data Workflow

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
