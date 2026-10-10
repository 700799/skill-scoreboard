# skill-scoreboard

**Measure whether your Claude Code skills actually earn their keep — then rank your whole library.**

A skill is just instructions in a Markdown file. That makes it easy to write and
impossible to evaluate by reading: a capable model often completes the task with
or without it. So "the tests passed" proves nothing about the skill, and a library
grows until nobody can say which entries help, which overlap, and which are quietly
costing tokens on every activation.

`skill-scoreboard` answers that with measurement instead of opinion. Every task runs
twice — **control** with skills disabled, **treatment** with the skill injected — and
the difference is the skill's value:

| metric | control | treatment | delta |
|---|---|---|---|
| pass rate | 0% | 100% | +100pp |
| mean total tokens | 65,400 | 33,575 | -48.7% |
| duplicate tool calls | 3.0 | 0.0 | -3.0 |
| file re-reads | 2.0 | 0.0 | -2.0 |
| skill activation | 0% | 100% | +100pp |

Point it at a whole directory of skills and it returns a ranked scoreboard with a
decision and a stated reason for each one:

| rank | skill | score | confidence | recommendation | reasons |
|---|---|---|---|---|---|
| 1 | `fastapi-schema` | 1.00 | 55% | **KEEP** | clears every tier that has run |
| 2 | `py-validation` | 1.00 | 15% | **MERGE → fastapi-schema** | overlaps fastapi-schema (similarity 0.55); fastapi-schema scores higher |
| 3 | `helpful-helper` | 0.43 | 15% | **FIX** | blocking lint findings: dead-reference; composite 0.43 is mid-range |

Both tables above are real output from the shipped examples, not mockups.

### What makes it more than a test runner

- **It catches the bypass.** A skill whose tasks pass while its *activation rate*
  stays low isn't working — the model is solving the problem from prior knowledge.
  That pattern gets flagged `FIX` instead of counted as success.
- **It measures waste, not just correctness.** Duplicate tool calls, re-reading
  large files without editing them, and runaway per-turn context growth are
  detected from the agent's trajectory.
- **It checks adherence structurally.** Python AST assertions verify the skill's
  prescribed constructs are present and its forbidden ones absent — so "used
  Pydantic v2 `@field_validator`, never the v1 `@validator`" is a test, not a hope.
- **It never fakes confidence.** Every score carries the share of evidence behind
  it. A skill with only a free static lint cannot outrank one measured end to end,
  and is never retired on thin evidence.
- **It runs offline.** Recorded sessions replay deterministically, so the whole
  suite — including the real `ruff`, `mypy`, and `pytest` evaluators — runs in CI
  with no API key.

### Two ways to use it

| | Command | Cost |
|---|---|---|
| **One skill, deeply** | `skill-scoreboard ab task.yaml` | Real agent runs |
| **A whole library** | `skill-scoreboard audit ./skills` → `rank` | Free static tier first, paid tiers only where they earn it |

---

## Install

```bash
pip install skill-scoreboard      # installs the `skill-scoreboard` command
```

From a checkout, for development:

```bash
uv venv && uv pip install -e ".[dev]"
```

Requires Python 3.11+. Live runs need the [Claude Code CLI](https://code.claude.com/docs)
on `PATH`; the LLM judge and critic need API credentials. **Everything else runs
offline** — pass `--no-llm` and `--runner replay` to work with no network at all.

## Quickstart

```bash
skill-scoreboard validate examples/tasks/*.yaml examples/probes.yaml       # schema-check
skill-scoreboard --no-llm audit examples/skills --json runs/audit.json     # Tier 0: lint + overlap
skill-scoreboard mine ~/.claude/projects --skills-dir examples/skills --json runs/mine.json
skill-scoreboard --no-llm ab examples/tasks/pydev-fastapi-pydantic-01.yaml \
    --runner replay --trials 2 \
    --control-fixture tests/fixtures/ndjson/loopy_no_skill.ndjson \
    --treatment-fixture tests/fixtures/ndjson/success_with_skill.ndjson
skill-scoreboard rank examples/skills --audit runs/audit.json --runs runs \
    --mine runs/mine.json --md runs/leaderboard.md
```

Drop `--runner replay` and its fixtures to run against the real CLI.

---

## The four measurements

### 1. Task success & code quality

`pydev_static` runs **ruff** and **mypy** over the final workspace; `pydev_tests`
runs **pytest**; `ast_assertions` parses the resulting code with Python's own
**AST** module. Missing tools degrade to a recorded failure rather than a crash.

### 2. Token waste & loop detection

Three anti-patterns, computed from the trajectory:

| Detector | What counts | Why it is not naive |
|---|---|---|
| Duplicate tool calls | Same tool + byte-identical input | Canonical JSON hashing; exempt list for legitimately repeated tools (`TodoWrite`) |
| Large-file re-reads | Re-reading a >100-line file | An `Edit`/`Write` to that file **resets** the window — re-reading your own change is legitimate |
| Context growth | Tokens added per turn (default limit 15k) | Exact when the stream carries per-message usage; falls back to a chars/4 estimate and **flags that it did** |

### 3. Skill adherence vs. generic bypass

The framework's sharpest signal. Three independent checks:

1. **`skill_activation`** — did the `Skill` tool actually fire for the target skill?
2. **`ast_assertions`** — are the skill's prescribed constructs present and its
   forbidden ones absent (e.g. Pydantic v2 `@field_validator` required,
   v1 `@validator` banned)?
3. **`llm_judge`** — a rubric graded by Claude for what static analysis can't see.

A skill whose tasks pass while activation stays low is flagged **FIX**: the model
is solving it from prior knowledge and the skill is along for the ride.

### 4. A/B baseline differential

Every task runs in two arms:

| Arm | How | Meaning |
|---|---|---|
| **Control** | `claude -p --disable-slash-commands` | What the model does unaided |
| **Treatment** | Skill injected at `.claude/skills/<name>/SKILL.md` | What the skill adds |

Reports give `treatment − control` deltas for pass rate, tokens, cost, duration,
and each waste metric. Negative token/cost deltas mean the skill *saves*.

> The control arm uses `--disable-slash-commands`, **not** `--bare`. `--bare`
> only skips hooks, LSP, and plugin credentials — its help notes that "Skills
> still resolve via `/skill-name`", so a `--bare` baseline would silently load
> the very skill under test and understate its measured value.

---

## Ranking a whole library

Cost scales with how deeply you want to probe, so a large library can be triaged
before spending real money:

| Tier | Command | Cost | Produces |
|---|---|---|---|
| **0 · Static** | `skill-scoreboard audit <dir>` | free | Lint findings + TF-IDF overlap clusters |
| **1 · Triggers** | `skill-scoreboard audit <dir> --probes probes.yaml` | cheap | Precision/recall/F1 + cross-activation confusion matrix |
| **2 · A/B** | `skill-scoreboard ab <task.yaml>` | real runs | Measured value lift |
| **Critic** | `skill-scoreboard audit <dir> --critic` | one call/skill | Actionable rewrite suggestions |
| **Mining** | `skill-scoreboard mine <transcripts>` | free | Real-world activation frequency and cost |

**Tier 0** catches the problems you can find for free: descriptions too vague to
route on, skills whose own body costs thousands of tokens on every activation,
dead file references, and near-duplicate skills that should be merged.

**Tier 1** asks whether a skill fires when it should — and stays quiet when it
shouldn't. Each skill's positive probes double as negatives for every *other*
skill, which fills a confusion matrix and exposes skills that keep firing on
each other's work (a merge signal independent of text similarity).

### Scoring

Composite score is a weighted mean over **whichever tiers have run**, with
weights renormalized across what's available — so a Tier 0-only library still
ranks, and the score sharpens as evidence accumulates.

```
lint 0.15 · trigger 0.25 · ab 0.40 · critic 0.20      (override with --weights)

ab = 0.50 × pass-rate lift + 0.25 × token savings + 0.25 × adherence
```

Recommendations, in precedence order:

- **RETIRE** — measured with no pass-rate lift, no token savings, and weak
  triggering; or a poor composite backed by real evidence; or never activated
  in mined sessions while scoring badly.
- **MERGE** — overlaps a higher-scoring sibling (TF-IDF cluster or
  cross-activation). `merge_with` names the survivor.
- **FIX** — blocking lint errors, trigger F1 below 0.70, a mid-range composite,
  or the bypass signature above.
- **KEEP** — clears every tier that has run.

**Confidence and ranking.** Renormalizing over available tiers alone would let a
skill with nothing but clean lint tie — or beat — one measured end to end and
found good. So each entry also carries a **confidence** (the share of scoring
weight actually backed by evidence), and *ranking* uses the composite shrunk
toward a neutral 0.5 in proportion to what's missing:

```
ranked = composite × confidence + 0.5 × (1 − confidence)
```

An unmeasured skill therefore cannot outrank a measured one, and the survivor of
a merge cluster is the best-*evidenced* member rather than the luckiest. The raw
composite is still what threshold decisions read, so the two roles stay separate.

**Guardrail:** a skill is never retired on static lint alone. With Tier 0 only,
the worst outcome is FIX, reason `insufficient_evidence`, and the leaderboard
prints `—` for every tier that didn't run. Thin evidence never impersonates a
measurement.

---

## Task schema

```yaml
id: pydev-fastapi-pydantic-01
description: "Verify the fastapi-schema skill refactors raw dicts into Pydantic v2 models."
target_skill: "../skills/fastapi-schema/SKILL.md"

workspace:
  initial_files:
    app.py: |
      from fastapi import FastAPI
      app = FastAPI()

prompt: "Refactor app.py to return a Pydantic model."

run_limits:
  max_turns: 6            # -> claude --max-turns
  max_budget_usd: 0.15    # -> claude --max-budget-usd
  # timeout_seconds, model, allowed_tools, disallowed_tools also supported

evaluations:
  - type: skill_activation
    expected: "fastapi-schema"
  - type: pydev_static
    linters: [ruff, mypy]
    strict: true
  - type: pydev_tests
  - type: ast_assertions
    assertions:
      - {file: app.py, kind: decorator_used, value: field_validator}
      - {file: app.py, kind: forbidden_decorator, value: validator}
  - type: trajectory_efficiency
    max_duplicate_tool_calls: 1
    max_file_re_reads: 2
  - type: llm_judge
    rubric: "Did the code use Pydantic V2 `@field_validator` syntax?"
```

The schema is strict: unknown fields and unknown evaluation types fail at load
time, not mid-run. `ast_assertions` kinds: `decorator_used`, `call_used`,
`import_used`, `class_inherits`, `function_defined`, and the `forbidden_*`
variants.

`probes.yaml` (for Tier 1) is documented in `examples/probes.yaml`.

---

## Architecture

Every measurement reads one normalized `Trajectory`, and three sources produce it:

```
claude -p --output-format stream-json ─┐
recorded NDJSON fixture ───────────────┼──> runner/ndjson.py ──> Trajectory ──> metrics
real session transcript (skill-scoreboard mine) ────┘                                   └──> evaluators
```

Because replay is a first-class source, the entire pipeline — including the
ruff/mypy/pytest evaluators — is exercised in CI with no API key and no network.
`ReplayRunner` re-applies the `Write`/`Edit` calls recorded in a fixture, so an
offline run rebuilds the workspace the agent actually produced instead of
grading the starting files.

Cost comes from the CLI's reported `total_cost_usd` when present; otherwise it
is estimated from a pricing table and **marked as estimated** in every report.

## Development

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest              # offline; live-marked tests are deselected by default
uv run pytest -m live      # needs an authenticated claude CLI, spends real tokens
python tests/fixtures/make_fixtures.py   # regenerate NDJSON fixtures
```

## Relationship to `claude plugin eval`

Claude Code ships an early-access, org-gated `claude plugin eval` that also runs
control/treatment arms with regex, tool-use, and LLM graders. This project is
standalone and complementary: it adds trajectory-level waste detection, AST
adherence checks, and portfolio-scale ranking, and it runs anywhere the CLI
runs. It is pinned against the `2.1.x` stream-json shape and parses defensively,
ignoring unknown event types and fields so format drift degrades rather than breaks.

## Releasing

Publishing runs on [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
via `.github/workflows/release.yml` — no API token is stored in this repository.

One-time setup, per index, at https://pypi.org/manage/account/publishing/
(and the same on test.pypi.org):

| Field | Value |
|---|---|
| PyPI project name | `skill-scoreboard` |
| Owner / repository | `700799` / `skill-scoreboard` |
| Workflow name | `release.yml` |
| Environment | `pypi` (`testpypi` on TestPyPI) |

Then:

```bash
# Dry run to TestPyPI first — Actions tab -> Release -> Run workflow -> testpypi
# Real release:
git tag v0.1.0 && git push origin v0.1.0
```

The workflow lints, type-checks, tests, builds, and runs `twine check` before
uploading, and **fails the build if the tag version disagrees with
`pyproject.toml`**. That guard matters: a version number can never be reused on
PyPI, even after deletion, so a wrong tag would otherwise burn it permanently.

To publish by hand with an API token instead (username is literally `__token__`):

```bash
uv build && uvx twine check dist/*
uvx twine upload dist/*
```

## License

MIT
