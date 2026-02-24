from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_agent.agent import ResearchPaperAgent
from research_agent.env import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Autonomous multi-step research-paper agent (Grok-centered)"
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Research question, e.g., 'Does hybrid retrieval improve multilingual literature reviews?'",
    )
    parser.add_argument(
        "--data",
        default="data/mock_papers.json",
        help="Path to mock paper dataset JSON",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full JSON result",
    )
    args = parser.parse_args()

    agent = ResearchPaperAgent(data_path=Path(args.data))
    result = agent.run(args.query)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"Mode: {result['mode']}")
    print("\nFinal Answer:")
    print(result["summary"].get("answer", ""))

    points = result["summary"].get("evidence_points", [])
    if points:
        print("\nEvidence:")
        for point in points:
            print(point)

    risks = result["summary"].get("risks", [])
    if risks:
        print("\nRisks:")
        for risk in risks:
            print(f"- {risk}")

    print("\nTop Citations:")
    for citation in result["citations"]:
        print(f"- {citation}")


if __name__ == "__main__":
    main()
