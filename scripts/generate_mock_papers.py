from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "data" / "mock_papers.json"
    target = root / "data" / "mock_papers.generated.json"
    shutil.copyfile(source, target)
    print(f"Generated mock dataset: {target}")


if __name__ == "__main__":
    main()

