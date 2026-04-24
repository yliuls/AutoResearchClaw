from __future__ import annotations

import dataclasses
import json
import time as _time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.pipeline._helpers import _safe_filename, _utcnow_iso, _write_jsonl
from researchclaw.pipeline.executor import StageResult, execute_stage
from researchclaw.pipeline.stages import Stage, StageStatus

_IDEA_STAGES: tuple[Stage, ...] = (
    Stage.LITERATURE_SCREEN,
    Stage.KNOWLEDGE_EXTRACT,
    Stage.SYNTHESIS,
    Stage.HYPOTHESIS_GEN,
    Stage.EXPERIMENT_DESIGN,
)


def _load_paper_payload(
    papers: str | Path | Mapping[str, Any] | Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if isinstance(papers, (str, Path)):
        path = Path(papers).expanduser().resolve()
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8")
        if suffix == ".jsonl":
            records = [
                json.loads(line)
                for line in text.splitlines()
                if line.strip()
            ]
        elif suffix == ".json":
            loaded = json.loads(text)
            if isinstance(loaded, list):
                records = loaded
            elif isinstance(loaded, dict):
                if isinstance(loaded.get("papers"), list):
                    records = loaded["papers"]
                else:
                    records = [loaded]
            else:
                raise ValueError(f"Unsupported JSON paper payload in {path}")
        elif suffix in {".yaml", ".yml"}:
            loaded = yaml.safe_load(text)
            if isinstance(loaded, list):
                records = loaded
            elif isinstance(loaded, dict):
                if isinstance(loaded.get("papers"), list):
                    records = loaded["papers"]
                else:
                    records = [loaded]
            else:
                raise ValueError(f"Unsupported YAML paper payload in {path}")
        else:
            raise ValueError(
                f"Unsupported paper input format: {path.suffix}. Use .json, .jsonl, .yaml, or .yml."
            )
    elif isinstance(papers, Mapping):
        records = [papers]
    else:
        records = list(papers)

    normalized: list[dict[str, Any]] = []
    for idx, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"Paper #{idx} must be a mapping, got {type(record).__name__}")
        normalized.append(_normalize_paper_record(record, idx))

    if not normalized:
        raise ValueError("No papers were provided")
    return normalized


def _normalize_paper_record(record: Mapping[str, Any], index: int) -> dict[str, Any]:
    title = str(record.get("title") or record.get("paper_title") or "").strip()
    abstract = str(record.get("abstract") or record.get("summary") or "").strip()
    if not title:
        raise ValueError(f"Paper #{index} is missing required field: title")
    if not abstract:
        raise ValueError(f"Paper #{index} is missing required field: abstract")

    authors_raw = record.get("authors", [])
    authors: list[dict[str, str]] = []
    if isinstance(authors_raw, Sequence) and not isinstance(authors_raw, (str, bytes)):
        for author in authors_raw:
            if isinstance(author, str) and author.strip():
                authors.append({"name": author.strip()})
            elif isinstance(author, Mapping):
                name = str(author.get("name", "")).strip()
                if name:
                    authors.append({"name": name})

    year_raw = record.get("year")
    try:
        year = int(year_raw) if year_raw is not None else 2024
    except (TypeError, ValueError):
        year = 2024

    cite_key = str(record.get("cite_key") or _safe_filename(title.lower())[:48]).strip() or f"paper_{index}"
    source = str(record.get("source") or "user_provided").strip() or "user_provided"
    url = str(record.get("url") or record.get("pdf_url") or "").strip()
    venue = str(record.get("venue") or "").strip()

    normalized = dict(record)
    normalized.update(
        {
            "id": str(record.get("id") or f"user-paper-{index}"),
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "year": year,
            "source": source,
            "url": url,
            "venue": venue,
            "cite_key": cite_key,
            "collected_at": str(record.get("collected_at") or _utcnow_iso()),
            "provided_by_user": True,
        }
    )
    return normalized


def _write_seed_literature(run_dir: Path, papers: list[dict[str, Any]]) -> tuple[str, ...]:
    stage_dir = run_dir / "stage-04"
    stage_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(stage_dir / "candidates.jsonl", papers)
    (stage_dir / "input_papers.json").write_text(
        json.dumps(
            {
                "count": len(papers),
                "papers": papers,
                "generated": _utcnow_iso(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (stage_dir / "search_meta.json").write_text(
        json.dumps(
            {
                "seeded_from_user_papers": True,
                "real_search": False,
                "total_candidates": len(papers),
                "ts": _utcnow_iso(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return ("candidates.jsonl", "input_papers.json", "search_meta.json")


def run_idea_generation_from_papers(
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    papers: str | Path | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    topic_override: str | None = None,
    auto_approve_gates: bool = True,
    verbose: bool = True,
) -> list[StageResult]:
    """Run the Stage 5→9 idea-generation chain from user-provided papers."""

    normalized_papers = _load_paper_payload(papers)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_seed_literature(run_dir, normalized_papers)

    effective_config = config
    if topic_override:
        effective_config = dataclasses.replace(
            config,
            research=dataclasses.replace(config.research, topic=topic_override),
        )

    results: list[StageResult] = []
    total_stages = len(_IDEA_STAGES)
    for idx, stage in enumerate(_IDEA_STAGES, start=1):
        prefix = f"[{run_id}] Stage {int(stage):02d}/{total_stages}"
        if verbose:
            print(f"{prefix} {stage.name} — running...", flush=True)
        t0 = _time.monotonic()
        result = execute_stage(
            stage,
            run_dir=run_dir,
            run_id=run_id,
            config=effective_config,
            adapters=adapters,
            auto_approve_gates=auto_approve_gates,
        )
        elapsed = _time.monotonic() - t0
        results.append(result)
        if verbose:
            if result.status == StageStatus.DONE:
                arts = ", ".join(result.artifacts) if result.artifacts else "none"
                print(f"{prefix} {stage.name} — done ({elapsed:.1f}s) → {arts}", flush=True)
            elif result.status == StageStatus.FAILED:
                err = result.error or "unknown error"
                print(f"{prefix} {stage.name} — FAILED ({elapsed:.1f}s) — {err}", flush=True)
            elif result.status == StageStatus.BLOCKED_APPROVAL:
                print(f"{prefix} {stage.name} — blocked (awaiting approval)", flush=True)
        if result.status is not StageStatus.DONE:
            break
    return results
