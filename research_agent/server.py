from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_agent.agent import ResearchPaperAgent
from research_agent.env import load_dotenv
from research_agent.pdf_ingest import convert_pdf_dir_to_dataset


def _json_response(handler: SimpleHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def create_handler(project_root: Path, default_data_path: Path) -> type[SimpleHTTPRequestHandler]:
    frontend_dir = project_root / "frontend"

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
                        "default_data_path": str(default_data_path),
                    },
                )
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
                self._run_agent(payload)
                return
            if parsed.path == "/api/ingest":
                self._ingest_pdf(payload)
                return

            _json_response(
                self,
                {"error": f"Unknown endpoint: {parsed.path}"},
                status=HTTPStatus.NOT_FOUND,
            )

        def _run_agent(self, payload: dict[str, Any]) -> None:
            query = (payload.get("query") or "").strip()
            if not query:
                _json_response(self, {"error": "query is required"}, status=400)
                return

            data_path = Path(payload.get("data_path") or default_data_path)
            if not data_path.is_absolute():
                data_path = project_root / data_path
            if not data_path.exists():
                _json_response(
                    self,
                    {"error": f"data file not found: {data_path}"},
                    status=400,
                )
                return

            try:
                agent = ResearchPaperAgent(data_path=data_path)
                result = agent.run(query)
            except Exception as exc:  # pragma: no cover - runtime guard
                _json_response(self, {"error": f"agent failed: {exc}"}, status=500)
                return

            _json_response(self, result, status=200)

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
    parser.add_argument("--data", default="data/mock_papers.json")
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

