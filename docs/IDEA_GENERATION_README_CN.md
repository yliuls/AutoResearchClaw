# Stage 5 到 Stage 9 独立 Idea Generation 使用说明

这个文档说明如何单独运行 `stage 5. LITERATURE_SCREEN` 到 `stage 9. EXPERIMENT_DESIGN`，用于测试 agent 的 idea 生成能力。

本次实现遵循两个原则：

- `stage 5 -> stage 9` 的原有逻辑不改
- 原有 stage 内部方法不改，只新增一个独立入口函数，把你提供的 paper 写成 `stage-04/candidates.jsonl`，然后复用现有 executor 继续执行

## 新增入口

Python 函数：

```python
from pathlib import Path

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.pipeline import run_idea_generation_from_papers

config = RCConfig.load("config.arc.yaml", check_paths=False)

results = run_idea_generation_from_papers(
    run_dir=Path("artifacts/idea-test"),
    run_id="idea-test",
    config=config,
    adapters=AdapterBundle(),
    papers="papers.json",
    topic_override="graph neural networks for molecular property prediction",
    auto_approve_gates=True,
)
```

CLI 命令：

```bash
researchclaw ideate \
  --config config.arc.yaml \
  --papers papers.json \
  --topic "graph neural networks for molecular property prediction" \
  --output artifacts/idea-test \
  --skip-preflight
```

默认会自动通过 `stage 5` 和 `stage 9` 的 gate，方便直接测试 idea 生成链路。

如果你希望保留 gate 停顿行为：

```bash
researchclaw ideate \
  --config config.arc.yaml \
  --papers papers.json \
  --require-approval
```

## 输入文件格式

支持：

- `.json`
- `.jsonl`
- `.yaml`
- `.yml`

### 最小字段

每篇 paper 至少需要：

- `title`
- `abstract`

### 可选字段

- `authors`
- `year`
- `url`
- `pdf_url`
- `venue`
- `cite_key`
- `source`

## 输入示例

### JSON 单篇

```json
{
  "title": "MolGraphX: Structure-aware graph learning for molecular property prediction",
  "abstract": "We study graph neural networks for molecular property prediction and analyze the effect of structure-aware message passing.",
  "authors": ["Alice Smith", "Bob Lee"],
  "year": 2024,
  "url": "https://example.com/molgraphx"
}
```

### JSON 多篇

```json
{
  "papers": [
    {
      "title": "Paper A",
      "abstract": "Abstract A"
    },
    {
      "title": "Paper B",
      "abstract": "Abstract B"
    }
  ]
}
```

### JSONL

```jsonl
{"title":"Paper A","abstract":"Abstract A"}
{"title":"Paper B","abstract":"Abstract B"}
```

### YAML

```yaml
papers:
  - title: Paper A
    abstract: Abstract A
  - title: Paper B
    abstract: Abstract B
```

## 运行时需要怎么配置

### 1. `research.topic`

这个字段仍然会被 `stage 5 -> stage 9` 使用，因为原始逻辑没有改。

建议：

- 最好把 `research.topic` 配成你要测试的 paper 对应方向
- 或者在新入口里传 `topic_override`
- 或者 CLI 使用 `--topic`

如果 topic 和 paper 完全不相关，`stage 5` 的关键词筛选会把输入 paper 过滤掉，后续结果会变差。

### 2. LLM 配置

如果你希望 agent 真正产出更强的 hypothesis / experiment plan，需要可用的 LLM 配置：

- `llm.provider`
- `llm.base_url`
- `llm.api_key_env` 或 `llm.api_key`
- `llm.primary_model`

如果没有可用 LLM，现有 stage 会走项目里原本就有的 fallback 逻辑。

### 3. 实验设计相关配置

`stage 9` 仍然会读取这些配置：

- `experiment.time_budget_sec`
- `experiment.metric_key`
- `experiment.metric_direction`

## 产出文件

新入口会先生成：

- `stage-04/candidates.jsonl`
- `stage-04/input_papers.json`
- `stage-04/search_meta.json`

然后继续复用原 pipeline 产物：

- `stage-05/shortlist.jsonl`
- `stage-06/cards/`
- `stage-07/synthesis.md`
- `stage-08/hypotheses.md`
- `stage-09/exp_plan.yaml`

## 适用场景

- 想只测 idea generation，不跑全 23 stages
- 想控制输入文献，只让 agent 基于你指定的 paper 出 idea
- 想比较不同 paper 输入下的 hypothesis / experiment design 质量

## 注意

- 这不是新的 stage 实现，只是新的入口函数
- `stage 5 -> stage 9` 的内部逻辑、prompt、fallback、gate 判断都保持原样
- 如果你要做严格对比实验，建议固定：
  - 相同 config
  - 相同 topic
  - 相同 LLM model
  - 仅替换 paper 输入文件
