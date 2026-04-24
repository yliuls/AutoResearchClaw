from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.pipeline.idea_generation import run_idea_generation_from_papers
from researchclaw.pipeline.stages import Stage, StageStatus


def _config_data(tmp_path: Path) -> dict[str, object]:
    return {
        "project": {"name": "idea-test", "mode": "docs-first"},
        "research": {
            "topic": "graph neural networks for molecular property prediction",
            "domains": ["ml"],
            "daily_paper_count": 5,
            "quality_threshold": 0.5,
        },
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "local"},
        "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost:1234/v1",
            "api_key_env": "TEST_KEY",
            "api_key": "test-key",
            "primary_model": "fake-model",
            "fallback_models": [],
        },
        "experiment": {"mode": "simulated", "time_budget_sec": 300},
    }


def test_run_idea_generation_from_papers_reuses_stage_5_to_9(
    tmp_path: Path, monkeypatch
) -> None:
    config = RCConfig.from_dict(_config_data(tmp_path), project_root=tmp_path, check_paths=False)
    run_dir = tmp_path / "run"

    from researchclaw.pipeline import executor as rc_executor

    monkeypatch.setattr(
        rc_executor.LLMClient,
        "from_rc_config",
        staticmethod(lambda _config: SimpleNamespace(config=SimpleNamespace(base_url="", api_key=""))),
    )

    results = run_idea_generation_from_papers(
        run_dir=run_dir,
        run_id="idea-test-run",
        config=config,
        adapters=AdapterBundle(),
        papers=[
            {
                "title": "MolGraphX: Structure-aware graph learning for molecular property prediction",
                "abstract": (
                    "We study graph neural networks for molecular property prediction "
                    "and analyze the effect of structure-aware message passing."
                ),
                "authors": ["Alice Smith", "Bob Lee"],
                "year": 2024,
                "url": "https://example.com/molgraphx",
            }
        ],
        auto_approve_gates=True,
    )

    assert [result.stage for result in results] == [
        Stage.LITERATURE_SCREEN,
        Stage.KNOWLEDGE_EXTRACT,
        Stage.SYNTHESIS,
        Stage.HYPOTHESIS_GEN,
        Stage.EXPERIMENT_DESIGN,
    ]
    assert all(result.status == StageStatus.DONE for result in results)

    assert (run_dir / "stage-04" / "candidates.jsonl").exists()
    assert (run_dir / "stage-04" / "input_papers.json").exists()
    assert (run_dir / "stage-05" / "shortlist.jsonl").exists()
    assert (run_dir / "stage-06" / "cards").is_dir()
    assert (run_dir / "stage-07" / "synthesis.md").exists()
    assert (run_dir / "stage-08" / "hypotheses.md").exists()
    assert (run_dir / "stage-09" / "exp_plan.yaml").exists()


def test_run_idea_generation_from_yaml_payload(
    tmp_path: Path, monkeypatch
) -> None:
    config = RCConfig.from_dict(_config_data(tmp_path), project_root=tmp_path, check_paths=False)
    run_dir = tmp_path / "run-yaml"
    papers_path = tmp_path / "papers.yaml"
    papers_path.write_text(
        yaml.safe_dump(
            {
                "papers": [
                    {
                        "title": "PromptDistill: Distilling reasoning traces into compact students",
                        "abstract": "We distill reasoning traces into smaller language models.",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    from researchclaw.pipeline import executor as rc_executor

    monkeypatch.setattr(
        rc_executor.LLMClient,
        "from_rc_config",
        staticmethod(lambda _config: SimpleNamespace(config=SimpleNamespace(base_url="", api_key=""))),
    )

    results = run_idea_generation_from_papers(
        run_dir=run_dir,
        run_id="idea-yaml-run",
        config=config,
        adapters=AdapterBundle(),
        papers=papers_path,
        topic_override="reasoning distillation for small language models",
        auto_approve_gates=True,
    )

    assert results[-1].stage == Stage.EXPERIMENT_DESIGN
    assert results[-1].status == StageStatus.DONE
    exp_plan = (run_dir / "stage-09" / "exp_plan.yaml").read_text(encoding="utf-8")
    assert "reasoning distillation for small language models" in exp_plan
