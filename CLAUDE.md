# Nordlys Multi-Agent Database System — ABB EV Charging Components

## Project Overview

**Goal**: Enrich a B2B database with companies that produce **mechanical components for EV charging stations**, with a focus on **extra-European markets** (Asia, North America, South America).

**Method**: A 3-level pipeline of AI agents (originally designed as Gemini Gems), each specialized in one task, optimized via DSPy.

---

## Agent Architecture

| Level | Agent | Role | Output |
|-------|-------|------|--------|
| 0 | Context Retriever | Scans web, aggregates macro-level sources | JSON: `technical_context` + prioritized sources |
| 1 | Research (Mechanical Extractor) | Extracts mechanical components from sources | JSON: `finished_product`, `semi_finished_product`, `raw_materials` |
| 2 | BOM Builder | Generates Bill of Materials per component | JSON: `BOM_tree` |
| 3 | Company Extractor | Finds real extra-European suppliers | JSON: `suppliers_found` |

---

## CURRENT TASK: DSPy Optimization of Agent 0 ONLY

> All other agents (1, 2, 3) are **out of scope** for this phase.

The objective is to **automatically optimize the system prompt** (instructions + few-shot demonstrations) of Agent 0 using the `dspy` Python package, following the procedures described in the official DSPy paper (`BootstrapFewShotWithRandomSearch` teleprompter).

The optimization file must be created as a standalone Python script: `optimize_agent0.py`.

---

## Agent 0 — Full Specification

### Identity (RODES Framework)

- **Role**: Senior Context Researcher and Data Forager specializing in the global EV charging infrastructure sector.
- **Objective**: Discover and aggregate diverse data sources related to EV charging stations — technical documentation, industry databases, e-commerce platforms, global trade fair exhibitor lists, and technical wikis. Supply the background knowledge that downstream agents (Level 1+) will use for surgical extraction.
- **Details**:
  - Prioritize sources in strict order: Priority 1 > Priority 2 > Priority 3.
  - Priority 1 — OEM technical datasheets, manuals, and patents (highest value).
  - Priority 2 — B2B industrial catalogs, directories, and trade fair exhibitor lists.
  - Priority 3 — Public datasets, GitHub repositories, technical standards, and general wikis.
  - Agent 0 must **NOT** extract specific mechanical components.
  - Agent 0 must **NOT** build supplier JSONs.
  - The count constraint is hard: `len(P1) > len(P2) > len(P3) >= 1`.
- **Examples**: All 10 labeled pairs in `Query_training_set.py`.
- **Style**: Pure JSON output — no text before `{`, no text after `}`, 2-space indentation.

### Input / Output Contract

**Input field name**: `ev_research_query`
A natural language question about EV charging station infrastructure, components, or technology.

**Output field name**: `json_response`
A valid JSON object with exactly four top-level keys:
- `technical_context` — a non-empty string with a brief technical background.
- `priority_1_sources` — list of objects with keys: `name`, `type` (datasheet|patent|manual), `manufacturer`, `relevance`, `search_query`.
- `priority_2_sources` — list of objects with keys: `name`, `type` (catalog|trade_fair|directory), `platform`, `relevance`, `search_query`.
- `priority_3_sources` — list of objects with keys: `name`, `type` (dataset|standard|wiki), `relevance`.

---

## Training Data

**File**: `Query_training_set.py`

Contains **10 labeled input-output pairs** (Pair_01 to Pair_10) covering:
DC fast charging, thermal management, enclosures/chassis, high-power connectors (CCS2/NACS/CHAdeMO), heavy-duty charging and pantographs, payment/RFID/HMI, AC Level 2 wallbox, SiC power electronics, cable management, and international certification (UL, GB/T, CHAdeMO).

**Recommended split for optimization**: 8 examples for training, 2 for validation.

The file is a raw JSON object. Each pair has the structure `{"Query_NN": "...", "Answer_NN": {...}}`. Parse it directly with `json.loads()` and wrap each pair into a `dspy.Example` with `ev_research_query` as input and `json_response` (the serialized answer JSON) as label.

---

## DSPy Optimization — Implementation Specification

### Target Script
Create `optimize_agent0.py` in the project root. It must be self-contained and executable.

### LM Configuration
Configure DSPy with **Google Gemini** as the target language model (e.g., `gemini-2.0-flash`). Use `dspy.configure(lm=...)` with the appropriate `dspy.LM` wrapper. The API key must be loaded from an environment variable, not hardcoded.

### DSPy Signature
Define a class-based signature (`dspy.Signature` subclass) named `Agent0Signature`. The docstring of the class serves as the system instruction for the LM — it must encode the full RODES specification of Agent 0 described above, including the priority ordering constraint and the prohibition against component extraction. Declare `ev_research_query` as an `InputField` and `json_response` as an `OutputField` with precise `desc` attributes that describe the expected JSON schema.

### DSPy Module
Define a class `Agent0` inheriting from `dspy.Module`. In `__init__`, declare a single `dspy.ChainOfThought(Agent0Signature)` predictor. In `forward`, pass the query through that predictor and return its output.

### Quality Metric
Define a Python function `agent0_metric(example, pred, trace=None)` returning a float in `[0.0, 1.0]`. The metric evaluates four independent criteria, each worth 0.25 points:
1. The `json_response` field is parseable as valid JSON (strip markdown fences if present).
2. All four required top-level keys are present in the parsed object.
3. The priority count constraint holds: `len(P1) > len(P2) > len(P3) >= 1`.
4. `technical_context` is a non-empty string of at least 50 characters.

### Teleprompter
Use `dspy.teleprompt.BootstrapFewShotWithRandomSearch` with the following parameters:
- `metric` — the `agent0_metric` function defined above.
- `max_bootstrapped_demos` — 3 (few-shot examples auto-generated and injected in the compiled prompt).
- `max_labeled_demos` — 4 (labeled examples drawn directly from the training set).
- `num_candidate_programs` — 10 (random search trials over demonstration selections).
- `num_threads` — 1 (increase only if the Gemini API rate limit permits parallel calls).

Call `teleprompter.compile(Agent0(), trainset=train_set, valset=val_set)` to produce the compiled program.

### Saving the Optimized Program
After compilation, call `.save("compiled_agent0.json")` on the compiled program. This file contains the optimized instructions and bootstrapped demonstrations and can be reloaded later via `.load("compiled_agent0.json")`.

### When to Switch Optimizer
The `BootstrapFewShotWithRandomSearch` teleprompter is appropriate for the current 10-example dataset. If the training set grows beyond 30 examples in the future, replace it with `dspy.teleprompt.MIPROv2` for stronger instruction optimization.

---

## File Structure

```
Nordlys-multi-A-database/
├── CLAUDE.md                                      # This file
├── Query_training_set.py                          # 10 labeled Q/A pairs for Agent 0
├── Multi-Agents System DB - ABB specific.pdf      # Project design document
├── DSPy.pdf                                       # DSPy paper (reference)
├── optimize_agent0.py                             # [TO CREATE] Optimization script
└── compiled_agent0.json                           # [GENERATED] Optimized Agent 0 weights
```

---

## Key Constraints and Rules

1. **Scope**: Only Agent 0 is being optimized in this phase. Do not modify or reference Agent 1, 2, or 3.
2. **Output format**: Agent 0 must always return pure JSON — no markdown code fences, no preamble text, no trailing prose.
3. **Priority count rule**: `len(P1) > len(P2) > len(P3) >= 1` is a hard structural constraint enforced by both the Signature field description and the metric.
4. **No component extraction**: Agent 0 aggregates sources only. Listing specific mechanical parts is Agent 1's exclusive domain.
5. **Training file**: `Query_training_set.py` is the ground truth and must not be modified.
6. **API key**: The Gemini API key must be read from the `GOOGLE_API_KEY` environment variable. Never hardcode credentials.
7. **Reproducibility**: After saving `compiled_agent0.json`, all future inference must load this file rather than re-running the compilation.

---

## Quick Reference: DSPy Concepts Used

| Concept | DSPy Entity | Purpose in This Project |
|---------|-------------|-------------------------|
| Signature | `dspy.Signature` subclass | Declares Agent 0 input/output schema and task instruction |
| Module | `dspy.ChainOfThought` | Adds step-by-step reasoning before JSON generation |
| Training example | `dspy.Example(...).with_inputs(...)` | Wraps each Q/A pair from `Query_training_set.py` |
| Metric | Python function `(example, pred, trace) -> float` | Scores JSON validity, schema correctness, priority ordering |
| Teleprompter | `BootstrapFewShotWithRandomSearch` | Bootstraps demonstrations + selects best via random search |
| Compile | `teleprompter.compile(program, trainset, valset)` | Returns the prompt-optimized Agent 0 program |
| Persist | `.save(path)` / `.load(path)` | Stores and reloads the compiled program |
