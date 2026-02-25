"""
optimize_agent0.py
------------------
DSPy optimization script for Agent 0 (Context Retriever).

Reads the 10 labeled Q/A pairs from Query_training_set_agent0.py, compiles Agent 0
using MIPROv2, which optimizes BOTH the instruction text (R, O, D, S) AND the
few-shot demonstrations (E) of the RODES system prompt.

Usage:
    export GOOGLE_API_KEY="your_key_here"   # or set in .env
    python optimize_agent0.py

Requires:
    pip install dspy-ai python-dotenv
"""

import json
import os
import time
from datetime import datetime

import dspy
from dspy.teleprompt import MIPROv2
import litellm

# ---------------------------------------------------------------------------
# Optional: load .env file if present (does not fail if file is absent)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on OS environment

# ---------------------------------------------------------------------------
# 1. LM CONFIGURATION
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemini/gemini-2.0-flash"  # test con Groq free tier (500K TPD); per produzione usare gemini/gemini-2.0-flash

api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise EnvironmentError(
        "GOOGLE_API_KEY environment variable is not set. "
        "Export it or add it to a .env file in the project root."
    )

lm = dspy.LM(
    GEMINI_MODEL,
    api_key=api_key,
    num_retries=10,     
    retry_delay=15
)

dspy.configure(lm=lm)

litellm.set_verbose = False
os.environ["LITELLM_RATE_LIMIT_RETRY_WAIT"] = "10"

# ---------------------------------------------------------------------------
# 2. SIGNATURE  (docstring = system instruction for Agent 0)
# ---------------------------------------------------------------------------
class Agent0Signature(dspy.Signature):
    """
    ROLE:
    You are a Senior Context Researcher and Data Forager specializing in the global
    electric vehicle (EV) infrastructure sector. Your exclusive role is to scan the web
    and gather broad, high-quality sources of information to build a rich contextual
    foundation for downstream analytical agents.

    OBJECTIVE:
    Discover and aggregate diverse data sources related to EV charging stations
    (technical documentation, industry databases, e-commerce platforms, global trade
    fair exhibitor lists, and technical wikis). When provided with a query about EV
    charging infrastructure, formulate searches to find macro-level information.
    Your output supplies the background knowledge that other agents will later use
    for surgical extraction.

    DETAILS:
    Prioritize sources in this strict order (always return at least 2 Priority 1,
    1 Priority 2, 1 Priority 3):
    - Priority 1 (HIGHEST): Technical product datasheets and manuals from OEM manufacturers
      (e.g., ABB Terra series, Siemens Sicharge, Tritium RTM). Also include relevant patents
      from Google Patents describing mechanical assemblies of EV charging stations. 
      These are the highest-value sources because they contain complete mechanical specifications. 
    - Priority 2: B2B industrial catalogs and directories (e.g., ThomasNet, RS Components,
      Misumi) listing specific mechanical components with specifications. Also include
      exhibitor lists and product catalogs from major trade fairs (e.g., Hannover Messe,
      Power2Drive, eMove360).
    - Priority 3: Public databases, GitHub repositories, or Kaggle datasets containing EV
      component data. Also include technical standards references (e.g., IEC 61851,
      IEC 62196) and general technical explanations of charging station construction.
    You must NOT extract specific mechanical components, nor build final supplier JSONs.
    Your output must strictly be a structured aggregation of sources and contextual
    explanations to enrich the system's database.

    STYLE:
    Return ONLY a valid JSON object. Start directly with '{' and end with '}'.
    No markdown code fences. No preamble text. No trailing prose. Use 2-space indentation.
    Keys must match the field schemas exactly:
    - priority_1_sources items → {type (Technical product datasheet|manual|patent), relevance, search_query}
    - priority_2_sources items → {type (catalog|trade_fair|directory), platform, relevance, search_query}
    - priority_3_sources items → {type (dataset|standard|wiki), relevance}
    """

    ev_research_query: str = dspy.InputField(
        desc="A natural language question about EV charging station infrastructure, components, or technology."
    )
    json_response: str = dspy.OutputField(
        desc=(
            "A pure JSON object (no markdown fences, no preamble) with exactly four keys: "
            "technical_context (string, ≥50 chars), "
            "priority_1_sources (list of {type, relevance, search_query}), "
            "priority_2_sources (list of {type, platform, relevance, search_query}), "
            "priority_3_sources (list of {type, relevance}). "
            "Minimum counts: at least 2 Priority 1 sources, at least 1 Priority 2, at least 1 Priority 3."
        )
    )


# ---------------------------------------------------------------------------
# 3. MODULE
# ---------------------------------------------------------------------------
class Agent0(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(Agent0Signature)

    def forward(self, ev_research_query: str):
        return self.predict(ev_research_query=ev_research_query)


# ---------------------------------------------------------------------------
# 4. TRAINING DATA LOADER
# ---------------------------------------------------------------------------
_TRAINING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_data", "Query_training_set_agent0.py")


def load_training_examples() -> list[dspy.Example]:
    """Parse Query_training_set.py (raw JSON despite .py extension) into dspy.Example objects.

    Handles the inconsistent key casing in the file:
      pair_1, pair_2, pair_03, pair_04, Pair_05 … Pair_10
    and the query/answer keys Query_NN / Answer_NN.
    """
    with open(_TRAINING_FILE, encoding="utf-8") as f:
        raw = f.read()

    data: dict = json.loads(raw)
    examples: list[dspy.Example] = []

    for pair_value in data.values():
        query_text = None
        answer_dict = None

        for key, val in pair_value.items():
            if key.lower().startswith("query"):
                query_text = val
            elif key.lower().startswith("answer"):
                answer_dict = val

        if query_text is None or answer_dict is None:
            print(f"[WARNING] Skipping malformed pair: {list(pair_value.keys())}")
            continue

        answer_str = json.dumps(answer_dict, ensure_ascii=False, indent=2)
        example = dspy.Example(
            ev_research_query=query_text,
            json_response=answer_str,
        ).with_inputs("ev_research_query")
        examples.append(example)

    return examples


# ---------------------------------------------------------------------------
# 5. QUALITY METRIC  (returns float in [0.0, 1.0])
# ---------------------------------------------------------------------------
def agent0_metric(example, pred, trace=None) -> float:
    """Score a prediction on four independent criteria worth 0.25 each.

    Criteria:
        1. json_response is parseable as valid JSON (after stripping fences).
        2. All four required top-level keys are present.
        3. Minimum source counts hold: len(P1) >= 2, len(P2) >= 1, len(P3) >= 1.
        4. technical_context is a non-empty string of at least 50 characters.
    """
    score = 0.0

    raw: str = getattr(pred, "json_response", "") or ""
    cleaned = raw.strip()

    # Strip markdown code fences if the model ignores the formatting rule
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    # --- Criterion 1: Valid JSON ---
    parsed = None
    try:
        parsed = json.loads(cleaned)
        score += 0.25
    except (json.JSONDecodeError, ValueError):
        return score  # Cannot evaluate further without a valid object

    # --- Criterion 2: Required keys present ---
    required = {"technical_context", "priority_1_sources", "priority_2_sources", "priority_3_sources"}
    if not required.issubset(parsed.keys()):
        return score
    score += 0.25

    # --- Criterion 3: Minimum source counts (aligned with training data) ---
    # Training set pattern: P1 >= 2, P2 >= 1, P3 >= 1 (no strict decreasing order)
    p1 = parsed.get("priority_1_sources", [])
    p2 = parsed.get("priority_2_sources", [])
    p3 = parsed.get("priority_3_sources", [])
    if all(isinstance(lst, list) for lst in (p1, p2, p3)):
        if len(p1) >= 2 and len(p2) >= 1 and len(p3) >= 1:
            score += 0.25

    # --- Criterion 4: Non-trivial technical_context ---
    tc = parsed.get("technical_context", "")
    if isinstance(tc, str) and len(tc.strip()) >= 50:
        score += 0.25

    return score

# ---------------------------------------------------------------------------
# 6. COMPILE AND SAVE
# ---------------------------------------------------------------------------
#_OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiled", "compiled_agent0.json")

def main() -> None:
    # 1. Fai partire il cronometro
    start_time = time.time()
    
    # 2. Crea la cartella con la data di oggi (es. "25-02-2026")
    today_str = datetime.now().strftime("%d-%m-%Y")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiled", today_str)
    os.makedirs(output_dir, exist_ok=True)
    
    compiled_path = os.path.join(output_dir, "compiled_agent0.json")
    metadata_path = os.path.join(output_dir, "metadata.json")

    print("=" * 60)
    print("Agent 0 — DSPy Optimization Pipeline")
    print(f"Model : {GEMINI_MODEL}")
    print(f"Output folder: {output_dir}")
    print("=" * 60)

    # Load and split data
    print("\n[1/4] Loading training examples …")
    all_examples = load_training_examples()
    if len(all_examples) < 2:
        raise ValueError(f"Need at least 2 examples; found {len(all_examples)}.")
    print(f"      Loaded {len(all_examples)} examples.")

    train_set = all_examples[:8]
    val_set = all_examples[8:]
    print(f"      Split → train: {len(train_set)}  |  val: {len(val_set)}")

    # Configure teleprompter
    print("\n[2/4] Configuring MIPROv2 …")
    teleprompter = MIPROv2(
        metric=agent0_metric,
        auto="light",
        num_threads=1,
    )
    print("      Teleprompter ready.")

    # Compile
    print("\n[3/4] Compiling Agent 0 (this will make multiple LLM calls) …")
    compiled_agent0 = teleprompter.compile(
        Agent0(),
        trainset=train_set,
        valset=val_set,
        max_bootstrapped_demos=2,
        max_labeled_demos=3,
    )
    print("      Compilation complete.")

    # Save & Metadata setup
    end_time = time.time()
    
    print(f"\n[4/4] Saving compiled program → {compiled_path}")
    compiled_agent0.save(compiled_path)
    print("      Saved.")

    # --- Quick inference smoke test ---
    print("\n" + "=" * 60)
    print("INFERENCE SMOKE TEST")
    print("=" * 60)
    test_query = (
        "Trovami fonti tecniche sui sistemi di raffreddamento a liquido "
        "per stazioni DC fast charging superiori a 150 kW."
    )
    print(f"Query: {test_query}\n")
    result = compiled_agent0(ev_research_query=test_query)
    response_preview = result.json_response[:600] if result.json_response else "(empty)"
    print(f"Response preview:\n{response_preview}\n…")
    score = agent0_metric(None, result)
    print(f"\nMetric score: {score:.2f} / 1.00")
    print("=" * 60)

    # Crea e salva il file metadata.json
    metadata = {
        "execution_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "running_time_minutes": round((end_time - start_time) / 60, 2),
        "model_used": GEMINI_MODEL,
        "final_metric_score": score,
        "optimization_specs": {
            "optimizer": "MIPROv2",
            "auto_mode": "light",
            "num_threads": 1,
            "max_bootstrapped_demos": 2,
            "max_labeled_demos": 3
        }
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
    print(f"[OK] Metadata saved in: {metadata_path}")

    if score < 0.75:
        print("[WARN] Score below 0.75 — consider increasing num_candidate_programs or expanding the training set.")
    else:
        print("[OK] Agent 0 compiled and validated successfully.")

if __name__ == "__main__":
    main()