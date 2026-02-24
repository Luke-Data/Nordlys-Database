# Nordlys Multi-Agent Database System

B2B database enrichment pipeline for **mechanical components of EV charging stations**, targeting extra-European markets (Asia, North America, South America).

## Architecture

A 4-level multi-agent pipeline, each agent specialized in one task:

| Agent | Role |
|-------|------|
| **0 — Context Retriever** | Scans the web and aggregates macro-level sources (datasheets, patents, trade fairs, catalogs) |
| **1 — Mechanical Extractor** | Extracts specific mechanical components from the sources |
| **2 — BOM Builder** | Generates a Bill of Materials per component |
| **3 — Company Extractor** | Finds real extra-European suppliers |

## Current Phase: Agent 0 Optimization

Agent 0 is being automatically optimized via **DSPy** (`BootstrapFewShotWithRandomSearch`) using 10 labeled Q/A pairs as training data.

**Entry point**: [optimization/optimize_agent0.py](optimization/optimize_agent0.py)

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your API key:

```
GOOGLE_API_KEY=your_key_here
```

## Project Structure

```
├── optimization/
│   ├── optimize_agent0.py          # DSPy optimization script for Agent 0
│   ├── compiled/                   # Compiled agent weights (.json)
│   └── training_data/
│       └── Query_training_set_agent0.py   # 10 labeled Q/A pairs
├── pipeline/                       # Agent pipeline (future phases)
├── outputs/                        # Pipeline outputs
├── docs/                           # Reference documents
└── requirements.txt
```

## Dependencies

- [dspy-ai](https://github.com/stanfordnlp/dspy) >= 2.5.0
- [python-dotenv](https://github.com/theskumar/python-dotenv) >= 1.0.0
- Google Gemini API (`gemini-2.0-flash`)
