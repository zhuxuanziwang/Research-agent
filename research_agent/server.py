from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlparse
import uuid

from research_agent.agent import ResearchPaperAgent
from research_agent.env import load_dotenv
from research_agent.pdf_ingest import convert_pdf_dir_to_dataset


def _json_response(
    handler: SimpleHTTPRequestHandler, payload: dict[str, Any], status: int = 200
) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def create_handler(
    project_root: Path, default_data_path: Path
) -> type[SimpleHTTPRequestHandler]:
    frontend_dir = project_root / "frontend"
    runs: dict[str, dict[str, Any]] = {}
    run_order: list[str] = []
    runs_lock = threading.Lock()
    max_run_history = 120

    def now_ts() -> float:
        return time.time()

    def _prune_runs() -> None:
        if len(run_order) <= max_run_history:
            return
        to_remove = len(run_order) - max_run_history
        for _ in range(to_remove):
            run_id = run_order.pop(0)
            runs.pop(run_id, None)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, directory=str(frontend_dir), **kwargs)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                _json_response(
                    self,
                    {
                        "status": "ok",
                        "mode": "live_only",
                        "default_data_path": str(default_data_path),
                    },
                )
                return

            if parsed.path.startswith("/api/runs/"):
                run_id = parsed.path.split("/api/runs/", 1)[1].strip()
                if not run_id:
                    _json_response(self, {"error": "run_id is required"}, status=400)
                    return
                with runs_lock:
                    run = runs.get(run_id)
                    if run is None:
                        _json_response(
                            self,
                            {"error": f"run not found: {run_id}"},
                            status=HTTPStatus.NOT_FOUND,
                        )
                        return
                    payload = dict(run)
                _json_response(self, payload, status=200)
                return

            if parsed.path in {"/", "/index.html"}:
                self.path = "/index.html"
            return super().do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                _json_response(self, {"error": "invalid JSON body"}, status=400)
                return

            if parsed.path == "/api/run":
                self._run_agent_async(payload)
                return
            if parsed.path == "/api/run-sync":
                self._run_agent_sync(payload)
                return
            if parsed.path == "/api/ingest":
                self._ingest_pdf(payload)
                return

            _json_response(
                self,
                {"error": f"Unknown endpoint: {parsed.path}"},
                status=HTTPStatus.NOT_FOUND,
            )

        def _resolve_data_path(self, payload: dict[str, Any]) -> Path:
            data_path = Path(payload.get("data_path") or default_data_path)
            if not data_path.is_absolute():
                data_path = project_root / data_path
            return data_path

        def _validate_run_payload(self, payload: dict[str, Any]) -> tuple[str, Path] | None:
            query = (payload.get("query") or "").strip()
            if not query:
                _json_response(self, {"error": "query is required"}, status=400)
                return None

            data_path = self._resolve_data_path(payload)
            if not data_path.exists():
                _json_response(
                    self,
                    {"error": f"data file not found: {data_path}"},
                    status=400,
                )
                return None
            return query, data_path

        def _run_agent_sync(self, payload: dict[str, Any]) -> None:
            validated = self._validate_run_payload(payload)
            if validated is None:
                return
            query, data_path = validated

            try:
                agent = ResearchPaperAgent(data_path=data_path)
                result = agent.run(
                    query,
                    include_full_trace=bool(payload.get("include_full_trace", False)),
                )
            except Exception as exc:  # pragma: no cover - runtime guard
                _json_response(self, {"error": f"agent failed: {exc}"}, status=500)
                return

            _json_response(self, result, status=200)

        def _run_agent_async(self, payload: dict[str, Any]) -> None:
            validated = self._validate_run_payload(payload)
            if validated is None:
                return
            query, data_path = validated
            include_full_trace = bool(payload.get("include_full_trace", False))

            run_id = uuid.uuid4().hex[:12]
            created = now_ts()
            run_state = {
                "run_id": run_id,
                "status": "queued",
                "query": query,
                "data_path": str(data_path),
                "created_at": created,
                "updated_at": created,
                "progress": {
                    "stage": "queued",
                    "message": "Queued.",
                    "step_index": 0,
                    "total_steps": 0,
                },
                "execution_trace": [],
                "error": "",
                "result": None,
            }
            with runs_lock:
                runs[run_id] = run_state
                run_order.append(run_id)
                _prune_runs()

            def progress_callback(event: dict[str, Any]) -> None:
                stage = event.get("stage", "running")
                message = "Running..."
                if stage == "planned":
                    total_steps = int(event.get("total_steps", 0))
                    message = f"Plan ready: {total_steps} step(s)."
                elif stage == "planning":
                    message = "Planning with Grok."
                elif stage == "step_started":
                    idx = int(event.get("step_index", 0))
                    total = int(event.get("total_steps", 0))
                    tool = event.get("tool", "unknown")
                    message = f"Step {idx}/{total} running via {tool}."
                elif stage == "step_finished":
                    idx = int(event.get("step_index", 0))
                    total = int(event.get("total_steps", 0))
                    message = f"Step {idx}/{total} completed."
                elif stage == "replanned":
                    added = int(event.get("added_steps", 0))
                    message = f"Replanned and added {added} step(s)."
                elif stage == "summarizing":
                    message = "Summarizing final answer."
                elif stage == "done":
                    message = "Completed."

                with runs_lock:
                    state = runs.get(run_id)
                    if state is None:
                        return
                    progress = dict(state.get("progress", {}))
                    progress["stage"] = stage
                    progress["message"] = message
                    if "step_index" in event:
                        progress["step_index"] = int(event.get("step_index", 0))
                    if "total_steps" in event:
                        progress["total_steps"] = int(event.get("total_steps", 0))
                    state["progress"] = progress
                    if stage == "step_finished" and event.get("trace_entry") is not None:
                        state["execution_trace"].append(event["trace_entry"])
                    state["updated_at"] = now_ts()

            def worker() -> None:
                with runs_lock:
                    state = runs.get(run_id)
                    if state is not None:
                        state["status"] = "running"
                        state["progress"] = {
                            "stage": "starting",
                            "message": "Initializing agent.",
                            "step_index": 0,
                            "total_steps": 0,
                        }
                        state["updated_at"] = now_ts()

                try:
                    agent = ResearchPaperAgent(data_path=data_path)
                    result = agent.run(
                        query,
                        include_full_trace=include_full_trace,
                        progress_callback=progress_callback,
                    )
                except Exception as exc:
                    with runs_lock:
                        state = runs.get(run_id)
                        if state is None:
                            return
                        state["status"] = "failed"
                        state["error"] = f"agent failed: {exc}"
                        state["progress"] = {
                            "stage": "failed",
                            "message": "Run failed.",
                            "step_index": state.get("progress", {}).get("step_index", 0),
                            "total_steps": state.get("progress", {}).get("total_steps", 0),
                        }
                        state["updated_at"] = now_ts()
                    return

                with runs_lock:
                    state = runs.get(run_id)
                    if state is None:
                        return
                    state["status"] = "completed"
                    state["result"] = result
                    state["progress"] = {
                        "stage": "completed",
                        "message": "Run completed.",
                        "step_index": state.get("progress", {}).get("step_index", 0),
                        "total_steps": state.get("progress", {}).get("total_steps", 0),
                    }
                    state["updated_at"] = now_ts()

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            _json_response(
                self,
                {
                    "run_id": run_id,
                    "status": "queued",
                },
                status=202,
            )

        def _ingest_pdf(self, payload: dict[str, Any]) -> None:
            pdf_dir = (payload.get("pdf_dir") or "").strip()
            out_path = (payload.get("output_path") or "data/real_papers.json").strip()
            metadata_csv = (payload.get("metadata_csv") or "").strip()
            id_prefix = (payload.get("id_prefix") or "REAL").strip()

            if not pdf_dir:
                _json_response(self, {"error": "pdf_dir is required"}, status=400)
                return

            source = Path(pdf_dir)
            if not source.is_absolute():
                source = project_root / source
            if not source.exists():
                _json_response(self, {"error": f"pdf dir not found: {source}"}, status=400)
                return

            destination = Path(out_path)
            if not destination.is_absolute():
                destination = project_root / destination

            metadata_path: Path | None = None
            if metadata_csv:
                metadata_path = Path(metadata_csv)
                if not metadata_path.is_absolute():
                    metadata_path = project_root / metadata_path

            try:
                result = convert_pdf_dir_to_dataset(
                    pdf_dir=source,
                    output_path=destination,
                    id_prefix=id_prefix,
                    metadata_csv=metadata_path,
                )
            except Exception as exc:  # pragma: no cover - runtime guard
                _json_response(self, {"error": f"ingest failed: {exc}"}, status=500)
                return

            _json_response(self, result, status=200)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return Handler


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run Research Agent web server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data", default="data/real_papers.json")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    default_data_path = Path(args.data)
    if not default_data_path.is_absolute():
        default_data_path = project_root / default_data_path

    handler = create_handler(project_root=project_root, default_data_path=default_data_path)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Research Agent UI running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
