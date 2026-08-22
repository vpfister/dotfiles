---
name: fermi-generation
description: Run, launch, and extend the Fermi question-generation tools in scripts/vpfister/fermi (interactive composer, ontology generator, solving UI, graph views). Use this skill whenever working on the Fermi benchmark generator — launching the marimo notebooks, running the CLI/tests, or adding motifs/quantity kinds.
---

# Fermi question generation — tools & launch reference

A Fermi-question **generator** (and solving substrate) in the mistral monorepo.

- **Location:** `scripts/vpfister/fermi/`
- **Worktree:** `~/workspace/mistral_fermi`  ·  **Branch:** `vincent.pfister/fermi`
- **Secrets:** worktree-root `~/workspace/mistral_fermi/.env` (gitignored, `chmod 600`) holds
  `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `SCIENCE_PRIVATE_ACCESS_ENV_VAR`. The marimo apps
  load it via `load_dotenv(find_dotenv())`; read variable **names** only, never values.

Always work from the fermi dir:
```
cd ~/workspace/mistral_fermi/scripts/vpfister/fermi
```

## Architecture in one breath

`dimensions.py` (DimensionVector = 7 SI exponents) + `quantity_kinds.py` (62 QUDT-validated
kinds) are the type system. The **dimensional engine validates; the LLM proposes/judges.**
Three generation paths share that substrate (see memories `fermi-generator` and
`fermi-composer-roadmap`).

---

## 1. Interactive composer — `compose_app.py`  (THE current working point)

Pick **entities** -> LLM profiles each entity's metrics -> `compose.py` enumerates
dimensionally-valid `ratio`/`mul` trees (multi-hop) -> LLM phrases each (with a `SKIP`
semantic veto for meaningless combos). Engine is pure/tested in `compose.py`.

- **Uses LLM:** yes (science endpoint — profiling + phrasing).
- **Deps:** `marimo rdflib python-dotenv httpx`.
- **UI controls:** entities text-area (one per line) · **Depth (hops) 1-3** slider ·
  Max questions 1-8 · Min OOM gap 0-6 · Generate button.

Launch (local, opens browser):
```
uv run --with marimo --with rdflib --with python-dotenv --with httpx marimo edit compose_app.py
```
Serve remotely on the cluster with a fixed token (reach it from your laptop):
```
uv run --with marimo --with rdflib --with python-dotenv --with httpx \
  marimo edit compose_app.py --host 0.0.0.0 --port 2718 --headless --token-password hgg2026
# then open  http://<this-host>:2718/?access_token=hgg2026
```
Read-only app mode (no editor): use `marimo run` instead of `marimo edit`.
Tips: try **dynamic entities** ("city", "coal power plant", "marathon") at **depth 2-3** for
non-trivial questions; static objects only yield the trivial "how many fit" ratio.

## 2. Ontology generator — graph view `generation_app.py` + CLI `generate.py`

Walks a small hand-built ontology (anchor -> typed hops collecting metrics), synthesises via a
generic op-tree (`generate.synthesize`), renders the question + a Mermaid graph
(`viz.to_mermaid`). Motifs in `motifs.py`: `energy_balance`, `solar_generation`.

- **Uses LLM:** no (deterministic graph traversal).
- **Deps:** `marimo rdflib`.

Graph view (motif dropdown -> answer + cheat sheet + node graph):
```
uv run --with marimo --with rdflib marimo edit generation_app.py
```
CLI (writes `generated_questions.jsonl`, one record per motif):
```
uv run --no-project --with rdflib python generate.py
```

## 3. Solving UI + reference models — `strategy_app.py`

Given a target quantity+entity, generates K decomposition **strategies** (LLM decompose +
dimensional gate), shows cross-strategy OOM agreement, plus per-model **reference** checkboxes
(gpt-5.5 / opus-4.8 / gemini-3.5 via OpenRouter; lazy-query + cache, cleared on Generate).

- **Uses LLM:** yes — science endpoint (decompose/anchor) **and** OpenRouter (`OPENROUTER_API_KEY`).
- **Deps:** `marimo rdflib httpx python-dotenv`.

```
uv run --with marimo --with rdflib --with httpx --with python-dotenv marimo edit strategy_app.py
```

## 4. Forward motif generator (older) — `generation.py`

`GenMotif`s: `count_fits`, `mass_ratio`, `area_fits`, `distance`, `fill_time`. Demo notebook
`generation_demo.py` (jupytext). Superseded by the composer; keep for reference.

---

## Tests, lint, commit

**Tests** (the env flags are REQUIRED — the monorepo root conftest + the project `.venv`'s
buildkite pytest plugin both break the ephemeral env; disabling autoload + setting PYTHONPATH
fixes both):
```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. \
  uv run --no-project --with rdflib --with pytest --with httpx pytest --noconftest --rootdir=. -q
```
Single offline module quick-check (no pytest):
```
PYTHONPATH=. uv run --no-project --with rdflib python -c "from compose import Metric, compose; ..."
```
**Lint** (from repo root `~/workspace/mistral_fermi`):
```
uvx prek run --files scripts/vpfister/fermi/<file> ...
```
**Commit style:** `fermi: <terse change>`; no co-author/AI lines. Push only when asked
(cluster SSH is intermittent — a `tail`-piped `git push` can mask a real failure; check the
real exit code, retry, or push from `~/workspace/mistral`).

## marimo gotchas

- marimo **reformats** the file on open/save (expands `return` tuples, indents `mo.md`).
  Commit the reformat; don't fight it.
- Each top-level variable may be assigned in **only one cell** — reusing a loop var name
  (e.g. `o`) across cells disables the colliding cell silently. Use distinct names.
- A UI element is created in one cell and **read in a downstream cell**; a cell can't react to
  its own widget's `.value`.
- After editing a running server, **restart it + hard-refresh** the browser.

## Extending

- **Add a quantity kind:** edit `quantity_kinds.py` (`QUANTITY_KINDS` dim + optional `SI_UNIT`);
  cross-validated against QUDT by `verify_against_qudt.py`.
- **Add an ontology motif:** add a `Motif` (slots + `synthesis` op-tree + `answer_dimension` +
  `answer_kind`) in `motifs.py` and a renderer in `template_nl.RENDERERS` — no engine code
  needed (synthesis is generic).
- **Composer behaviour** lives in `compose.py` (`compose()`, `kind_for_dimension`, `_score`
  ranking) — keep it pure and tested; LLM profiling/phrasing prompts live in `compose_app.py`.

## Legacy jupytext spikes (exploratory, superseded)

`fermi_spike.py`, `generation_spike.py`, `validation_spike.py`, `generation_demo.py`,
`fermi_demo.py` are jupytext percent-notebooks from earlier exploration. Run via jupyterlab:
```
uv run --no-project --with rdflib --with httpx --with python-dotenv --with jupyterlab --with jupytext \
  jupyter lab
```
Prefer the marimo apps above; these are kept for reference only.
