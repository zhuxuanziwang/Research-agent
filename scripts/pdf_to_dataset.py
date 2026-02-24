from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.pdf_ingest import convert_pdf_dir_to_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a directory of PDF papers into data JSON for ResearchPaperAgent."
    )
    parser.add_argument("--pdf-dir", required=True, help="Directory containing .pdf files")
    parser.add_argument(
        "--out",
        default="data/real_papers.json",
        help="Output dataset path (JSON)",
    )
    parser.add_argument(
        "--id-prefix",
        default="REAL",
        help="Prefix used for generated paper_id, e.g., REAL-001",
    )
    parser.add_argument(
        "--metadata-csv",
        default=None,
        help="Optional CSV with filename-level metadata",
    )
    args = parser.parse_args()

    result = convert_pdf_dir_to_dataset(
        pdf_dir=Path(args.pdf_dir),
        output_path=Path(args.out),
        id_prefix=args.id_prefix,
        metadata_csv=Path(args.metadata_csv) if args.metadata_csv else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
