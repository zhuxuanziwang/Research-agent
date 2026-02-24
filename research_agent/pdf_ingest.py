from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
from typing import Any


PDF_ID_PATTERN = re.compile(r"[A-Za-z]{2,6}-\d{2,5}")
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z\u00C0-\u024F\u4e00-\u9fff]{3,}")


SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "abstract": ("abstract", "摘要", "resumen"),
    "methodology": (
        "methodology",
        "methods",
        "method",
        "approach",
        "materials and methods",
        "方法",
        "metodología",
    ),
    "findings": (
        "results",
        "findings",
        "evaluation",
        "discussion",
        "结论",
        "结果",
        "hallazgos",
        "resultados",
    ),
    "limitations": (
        "limitations",
        "threats to validity",
        "future work",
        "局限性",
        "限制",
        "limitaciones",
        "trabajo futuro",
    ),
}


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "using",
    "paper",
    "study",
    "results",
    "method",
    "methods",
    "model",
    "analysis",
    "across",
    "over",
    "between",
    "also",
    "pero",
    "para",
    "con",
    "del",
    "los",
    "las",
    "una",
    "este",
    "esta",
}


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _heading_matches(line: str, candidates: tuple[str, ...]) -> bool:
    line = line.strip().lower().strip(":：")
    if not line:
        return False
    for candidate in candidates:
        if line == candidate or line.startswith(candidate + " "):
            return True
    return False


def _find_heading_positions(text: str) -> list[tuple[int, str]]:
    positions: list[tuple[int, str]] = []
    for match in re.finditer(r"(?m)^[^\n]{2,120}$", text):
        line = match.group(0)
        for section, labels in SECTION_HEADINGS.items():
            if _heading_matches(line, labels):
                positions.append((match.start(), section))
                break
    positions.sort(key=lambda item: item[0])
    return positions


def _slice_sections_by_heading(text: str) -> dict[str, str]:
    positions = _find_heading_positions(text)
    sections: dict[str, str] = {}
    if not positions:
        return sections

    for index, (start, section) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        chunk = text[start:end]
        first_line_end = chunk.find("\n")
        if first_line_end >= 0:
            chunk = chunk[first_line_end + 1 :]
        cleaned = normalize_text(chunk)
        if cleaned and section not in sections:
            sections[section] = cleaned
    return sections


def _paragraph_fallback(text: str) -> dict[str, str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 120]
    if not paragraphs:
        return {
            "abstract": text[:1500],
            "methodology": text[:1200],
            "findings": text[1200:2800],
            "limitations": text[-1200:],
        }

    abstract = paragraphs[0]
    methodology = next(
        (p for p in paragraphs if re.search(r"\b(method|approach|dataset|实验|方法)\b", p, re.I)),
        paragraphs[min(1, len(paragraphs) - 1)],
    )
    findings = next(
        (p for p in paragraphs if re.search(r"\b(result|finding|improv|error|结论|结果)\b", p, re.I)),
        paragraphs[min(2, len(paragraphs) - 1)],
    )
    limitations = next(
        (
            p
            for p in paragraphs
            if re.search(r"\b(limit|future work|threat|不足|局限|limitaciones)\b", p, re.I)
        ),
        paragraphs[-1],
    )
    return {
        "abstract": normalize_text(abstract),
        "methodology": normalize_text(methodology),
        "findings": normalize_text(findings),
        "limitations": normalize_text(limitations),
    }


def split_sections(text: str) -> dict[str, str]:
    text = normalize_text(text)
    if not text:
        return {
            "abstract": "",
            "methodology": "",
            "findings": "",
            "limitations": "",
        }

    sections = _slice_sections_by_heading(text)
    if not sections:
        sections = _paragraph_fallback(text)
    else:
        fallback = _paragraph_fallback(text)
        for key in ("abstract", "methodology", "findings", "limitations"):
            sections.setdefault(key, fallback.get(key, ""))

    return {key: normalize_text(sections.get(key, "")) for key in ("abstract", "methodology", "findings", "limitations")}


def infer_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"\b(el|la|los|las|una|este|metodolog[ií]a|resultados)\b", text, re.I):
        return "es"
    return "en"


def infer_stance(text: str) -> str:
    low = text.lower()
    positive = any(
        token in low for token in ("improve", "outperform", "robust", "gain", "提升", "mejora")
    )
    negative = any(
        token in low for token in ("fail", "degrade", "unstable", "drop", "局限", "falla", "bias")
    )
    if positive and negative:
        return "mixed"
    if positive:
        return "supports"
    if negative:
        return "challenges"
    return "mixed"


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    tokens = [tok.lower() for tok in TOKEN_PATTERN.findall(text)]
    counts: dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [token for token, _ in ranked[:limit]]


def extract_citations(text: str, limit: int = 12) -> list[str]:
    ids = PDF_ID_PATTERN.findall(text)
    dois = DOI_PATTERN.findall(text)
    merged: list[str] = []
    for item in ids + dois:
        if item not in merged:
            merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _extract_text_with_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""

    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def _extract_text_with_pdftotext(path: Path) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def extract_pdf_text(path: Path) -> str:
    text = _extract_text_with_pypdf(path)
    if text.strip():
        return normalize_text(text)
    text = _extract_text_with_pdftotext(path)
    if text.strip():
        return normalize_text(text)
    return ""


@dataclass(slots=True)
class MetadataRecord:
    paper_id: str | None = None
    title: str | None = None
    year: int | None = None
    language: str | None = None
    venue: str | None = None
    authors: list[str] | None = None
    keywords: list[str] | None = None


def load_metadata_csv(path: str | Path | None) -> dict[str, MetadataRecord]:
    if not path:
        return {}
    metadata_path = Path(path)
    if not metadata_path.exists():
        return {}

    table: dict[str, MetadataRecord] = {}
    with metadata_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            filename = (row.get("filename") or "").strip()
            if not filename:
                continue
            authors = [item.strip() for item in (row.get("authors") or "").split(";") if item.strip()]
            keywords = [item.strip() for item in (row.get("keywords") or "").split(";") if item.strip()]
            year_value = (row.get("year") or "").strip()
            year = int(year_value) if year_value.isdigit() else None
            table[filename] = MetadataRecord(
                paper_id=(row.get("paper_id") or "").strip() or None,
                title=(row.get("title") or "").strip() or None,
                year=year,
                language=(row.get("language") or "").strip() or None,
                venue=(row.get("venue") or "").strip() or None,
                authors=authors or None,
                keywords=keywords or None,
            )
    return table


def _build_paper_id(index: int, stem: str, prefix: str) -> str:
    match = re.search(r"(\d{2,5})", stem)
    serial = match.group(1) if match else f"{index + 1:03d}"
    return f"{prefix}-{serial}"


def convert_pdf_to_record(
    pdf_path: Path,
    index: int,
    id_prefix: str = "REAL",
    metadata: MetadataRecord | None = None,
) -> dict[str, Any] | None:
    text = extract_pdf_text(pdf_path)
    if len(text) < 80:
        return None

    sections = split_sections(text)
    title = metadata.title if metadata and metadata.title else pdf_path.stem.replace("_", " ")
    language = metadata.language if metadata and metadata.language else infer_language(text[:5000])
    year = metadata.year if metadata and metadata.year else datetime.now().year
    keywords = metadata.keywords if metadata and metadata.keywords else extract_keywords(text)
    citations = extract_citations(text)
    stance = infer_stance(sections["findings"] + "\n" + sections["limitations"])
    paper_id = metadata.paper_id if metadata and metadata.paper_id else _build_paper_id(index, pdf_path.stem, id_prefix)
    venue = metadata.venue if metadata and metadata.venue else "Unknown venue (PDF import)"
    authors = metadata.authors if metadata and metadata.authors else ["Unknown"]

    return {
        "paper_id": paper_id,
        "title": title,
        "year": year,
        "language": language,
        "venue": venue,
        "authors": authors,
        "abstract": sections["abstract"],
        "methodology": sections["methodology"],
        "findings": sections["findings"],
        "limitations": sections["limitations"],
        "citations": citations,
        "keywords": keywords,
        "stance": stance,
    }


def convert_pdf_dir_to_dataset(
    pdf_dir: str | Path,
    output_path: str | Path,
    id_prefix: str = "REAL",
    metadata_csv: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(pdf_dir)
    destination = Path(output_path)
    metadata_map = load_metadata_csv(metadata_csv)

    pdf_files = sorted(source.glob("*.pdf"))
    records: list[dict[str, Any]] = []
    skipped: list[str] = []

    for index, pdf_path in enumerate(pdf_files):
        metadata = metadata_map.get(pdf_path.name)
        record = convert_pdf_to_record(
            pdf_path=pdf_path,
            index=index,
            id_prefix=id_prefix,
            metadata=metadata,
        )
        if record is None:
            skipped.append(pdf_path.name)
            continue
        records.append(record)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "pdf_count": len(pdf_files),
        "record_count": len(records),
        "skipped": skipped,
        "output": str(destination),
    }

