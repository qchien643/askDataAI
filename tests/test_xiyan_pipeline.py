"""
XiYan Pipeline — Ground Truth Test Suite.

Test methodology:
1. Backup the full models.yaml as ground truth
2. Strip descriptions from 3 test tables (customers, products, internet_sales)
   while keeping the other 9 tables intact as reference examples
3. Run the XiYan pipeline on the stripped version
4. Compare AI-generated descriptions vs ground truth using LLM-as-Judge

Metrics:
- Semantic Accuracy: LLM judge scores 1-5 per description
- Enum Detection Rate: % of enum values correctly identified
- Style Consistency: Does AI output match the writing style of existing descriptions
"""

import asyncio
import copy
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from askdataai.config import settings
from askdataai.generation.llm_client import LLMClient
from askdataai.modeling.manifest_builder import ManifestBuilder

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────

# Tables to strip descriptions from (test subjects)
TEST_TABLES = ["customers", "products", "internet_sales"]

# Tables that keep descriptions (reference examples for the agent)
# All other tables remain intact as few-shot context

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.yaml"
STRIPPED_PATH = Path(__file__).parent / "stripped_models.yaml"
RESULTS_PATH = Path(__file__).parent / "test_results.json"
MODELS_YAML = Path(__file__).parent.parent / "models.yaml"


# ─── Step 1: Create Ground Truth ──────────────────────────────

def create_ground_truth():
    """
    Backup current models.yaml as ground truth.

    Returns:
        dict: Ground truth data for test tables only.
              Format: {table_name: {col_name: {"description": ..., "enum_values": [...]}}}
    """
    with open(MODELS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    ground_truth = {}
    for model in data.get("models", []):
        name = model.get("name", "")
        if name not in TEST_TABLES:
            continue

        ground_truth[name] = {}
        for col in model.get("columns", []):
            col_name = col.get("name", "")
            ground_truth[name][col_name] = {
                "description": col.get("description", ""),
                "enum_values": col.get("enum_values", []),
                "type": col.get("type", ""),
            }

    # Save ground truth
    with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
        yaml.dump(ground_truth, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120)

    total_cols = sum(len(cols) for cols in ground_truth.values())
    print(f"✅ Ground truth created: {len(ground_truth)} tables, {total_cols} columns")
    print(f"   Saved to: {GROUND_TRUTH_PATH}")

    for table, cols in ground_truth.items():
        described = sum(1 for c in cols.values() if c["description"])
        print(f"   - {table}: {len(cols)} columns ({described} with descriptions)")

    return ground_truth


# ─── Step 2: Create Stripped Models ───────────────────────────

def create_stripped_models():
    """
    Create a stripped version of models.yaml where test tables
    have their descriptions removed.

    Returns:
        Path to stripped_models.yaml
    """
    with open(MODELS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    stripped_count = 0
    for model in data.get("models", []):
        name = model.get("name", "")
        if name not in TEST_TABLES:
            continue

        for col in model.get("columns", []):
            if col.get("description", "").strip():
                col["description"] = ""
                stripped_count += 1
            # Also remove enum_values to test enum detection
            if col.get("enum_values"):
                col["enum_values"] = []

    with open(STRIPPED_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120)

    print(f"✅ Stripped models created: {stripped_count} descriptions removed")
    print(f"   Saved to: {STRIPPED_PATH}")
    return STRIPPED_PATH


# ─── Step 3: Run Pipeline ─────────────────────────────────────

async def run_pipeline_on_stripped() -> dict[str, dict]:
    """
    Run the XiYan pipeline on stripped models and collect results.

    Returns:
        Dict: {table_name: {col_name: {"description": ..., "enum_values": [...]}}}
    """
    import shutil

    # Backup original models.yaml
    backup_path = MODELS_YAML.with_suffix(".yaml.bak")
    shutil.copy2(MODELS_YAML, backup_path)
    print(f"📦 Backed up models.yaml → {backup_path}")

    try:
        # Replace with stripped version
        shutil.copy2(STRIPPED_PATH, MODELS_YAML)
        print("📝 Using stripped models.yaml for pipeline run")

        # Run pipeline
        from askdataai.generation.auto_describe.pipeline import DescriptionPipeline, PipelineConfig

        pipeline = DescriptionPipeline(settings)
        config = PipelineConfig(
            mode="overwrite",
            tables=TEST_TABLES,
        )

        print("\n🚀 Running XiYan pipeline...")
        results: dict[str, dict] = {}

        async for event in pipeline.run_stream(config):
            status_icon = {"running": "⏳", "done": "✅", "error": "❌"}.get(
                event.status, "•"
            )
            print(f"  {status_icon} [{event.phase}] {event.progress}")

            # Collect agent results
            if event.phase == "agent" and event.status == "done":
                if "descriptions" in event.data:
                    results[event.table] = event.data["descriptions"]

        return results

    finally:
        # Restore original models.yaml
        shutil.copy2(backup_path, MODELS_YAML)
        backup_path.unlink()
        print(f"\n📦 Restored original models.yaml")


# ─── Step 4: LLM-as-Judge Evaluation ─────────────────────────

JUDGE_PROMPT = """You are evaluating AI-generated database column descriptions against human-written ground truth.

Column: {table}.{column} (type: {col_type})

GROUND TRUTH (human-written):
"{ground_truth}"

AI GENERATED:
"{ai_generated}"

Score the AI description on each dimension (1-5):

1. **Semantic Accuracy** (1-5): Does it correctly describe what the column contains?
   - 5: Perfectly accurate, captures the same meaning
   - 3: Partially correct, misses some nuances
   - 1: Incorrect or misleading

2. **Completeness** (1-5): Does it include all important information?
   - 5: All key info present (enum values, units, FK refs, etc.)
   - 3: Some info missing but usable
   - 1: Major information gaps

3. **Style Match** (1-5): Does it follow the same writing style as the ground truth?
   - 5: Same format, length, and conventions
   - 3: Different style but readable
   - 1: Completely different style

Return JSON:
{{
    "semantic_accuracy": <1-5>,
    "completeness": <1-5>,
    "style_match": <1-5>,
    "overall": <1-5>,
    "notes": "<brief explanation>"
}}"""


async def evaluate_with_judge(
    ground_truth: dict[str, dict],
    ai_results: dict[str, dict],
    llm: LLMClient,
) -> dict[str, Any]:
    """
    Evaluate AI results against ground truth using LLM-as-Judge.

    Returns:
        Evaluation summary with per-column scores and aggregates.
    """
    evaluations = []
    enum_matches = {"correct": 0, "total": 0}

    for table_name, cols in ground_truth.items():
        ai_table = ai_results.get(table_name, {})

        for col_name, gt_data in cols.items():
            gt_desc = gt_data.get("description", "")
            gt_enums = gt_data.get("enum_values", [])
            col_type = gt_data.get("type", "")

            ai_desc = ai_table.get(col_name, "")
            ai_enums = []

            # Handle dict format from agent
            if isinstance(ai_desc, dict):
                ai_enums = ai_desc.get("enum_values", [])
                ai_desc = ai_desc.get("description", "")

            if not gt_desc:
                continue

            # LLM-as-Judge scoring
            prompt = JUDGE_PROMPT.format(
                table=table_name,
                column=col_name,
                col_type=col_type,
                ground_truth=gt_desc,
                ai_generated=ai_desc or "(empty - no description generated)",
            )

            try:
                scores = llm.chat_json(
                    user_prompt=prompt,
                    system_prompt="You are a fair and precise evaluation judge.",
                    temperature=0.0,
                )
            except Exception as e:
                logger.warning(f"Judge failed for {table_name}.{col_name}: {e}")
                scores = {
                    "semantic_accuracy": 0, "completeness": 0,
                    "style_match": 0, "overall": 0, "notes": f"Judge error: {e}"
                }

            evaluations.append({
                "table": table_name,
                "column": col_name,
                "type": col_type,
                "ground_truth": gt_desc,
                "ai_generated": ai_desc,
                "scores": scores,
            })

            # Enum detection check
            if gt_enums:
                enum_matches["total"] += len(gt_enums)
                for val in gt_enums:
                    if val in ai_enums:
                        enum_matches["correct"] += 1

    # Aggregate scores
    if evaluations:
        avg_scores = {
            "semantic_accuracy": _avg([e["scores"].get("semantic_accuracy", 0) for e in evaluations]),
            "completeness": _avg([e["scores"].get("completeness", 0) for e in evaluations]),
            "style_match": _avg([e["scores"].get("style_match", 0) for e in evaluations]),
            "overall": _avg([e["scores"].get("overall", 0) for e in evaluations]),
        }
    else:
        avg_scores = {"semantic_accuracy": 0, "completeness": 0, "style_match": 0, "overall": 0}

    enum_rate = (
        enum_matches["correct"] / enum_matches["total"] * 100
        if enum_matches["total"] > 0 else 0
    )

    summary = {
        "total_evaluated": len(evaluations),
        "average_scores": avg_scores,
        "enum_detection_rate": f"{enum_rate:.1f}%",
        "enum_matches": enum_matches,
        "evaluations": evaluations,
        "pass": avg_scores.get("overall", 0) >= 3.5,
    }

    return summary


def _avg(values: list) -> float:
    valid = [v for v in values if isinstance(v, (int, float)) and v > 0]
    return round(sum(valid) / len(valid), 2) if valid else 0.0


# ─── Step 5: Report ───────────────────────────────────────────

def print_report(summary: dict):
    """Print a formatted evaluation report."""
    print("\n" + "=" * 70)
    print("  📊 XIYAN PIPELINE — EVALUATION REPORT")
    print("=" * 70)

    scores = summary.get("average_scores", {})
    print(f"\n  Total Evaluated:     {summary['total_evaluated']} columns")
    print(f"  Semantic Accuracy:   {scores.get('semantic_accuracy', 0)}/5.0")
    print(f"  Completeness:        {scores.get('completeness', 0)}/5.0")
    print(f"  Style Match:         {scores.get('style_match', 0)}/5.0")
    print(f"  Overall:             {scores.get('overall', 0)}/5.0")
    print(f"  Enum Detection:      {summary.get('enum_detection_rate', '0%')}")

    passed = summary.get("pass", False)
    print(f"\n  Result:              {'✅ PASS' if passed else '❌ FAIL'} (threshold: 3.5/5.0)")

    # Per-table breakdown
    print(f"\n  {'─' * 60}")
    print(f"  Per-Table Breakdown:")

    table_scores: dict[str, list] = {}
    for ev in summary.get("evaluations", []):
        table = ev["table"]
        if table not in table_scores:
            table_scores[table] = []
        table_scores[table].append(ev["scores"].get("overall", 0))

    for table, scores_list in table_scores.items():
        avg = _avg(scores_list)
        print(f"    {table}: {avg}/5.0 ({len(scores_list)} columns)")

    # Bottom 5 descriptions (worst scores)
    evals = summary.get("evaluations", [])
    sorted_evals = sorted(evals, key=lambda e: e["scores"].get("overall", 0))
    bottom = sorted_evals[:5]

    if bottom:
        print(f"\n  {'─' * 60}")
        print(f"  Bottom 5 (needs improvement):")
        for ev in bottom:
            score = ev["scores"].get("overall", 0)
            notes = ev["scores"].get("notes", "")[:60]
            print(f"    [{score}/5] {ev['table']}.{ev['column']}: {notes}")

    print("\n" + "=" * 70)


# ─── Main ─────────────────────────────────────────────────────

async def main():
    """Run the complete test suite."""
    print("🧪 XiYan Pipeline — Ground Truth Test Suite")
    print("=" * 50)

    # Step 1: Create ground truth
    print("\n📋 Step 1: Creating ground truth...")
    ground_truth = create_ground_truth()

    # Step 2: Create stripped models
    print("\n📋 Step 2: Creating stripped models...")
    create_stripped_models()

    # Step 3: Run pipeline
    print("\n📋 Step 3: Running XiYan pipeline...")
    ai_results = await run_pipeline_on_stripped()

    # Step 4: Evaluate
    print("\n📋 Step 4: Evaluating with LLM-as-Judge...")
    llm = LLMClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    summary = await evaluate_with_judge(ground_truth, ai_results, llm)

    # Step 5: Report
    print_report(summary)

    # Save results
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 Full results saved to: {RESULTS_PATH}")

    return summary


if __name__ == "__main__":
    asyncio.run(main())
