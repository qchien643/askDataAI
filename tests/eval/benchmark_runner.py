"""Benchmark runner for askDataAI Text-to-SQL pipeline.

Workflow:
  1. Load benchmark_dataset.yaml
  2. For each example:
     a. Execute gold_sql directly on AdventureWorks
     b. POST /v1/ask to running backend with question_vi
     c. Compare results — fast path (canonical exec_match), fallback LLM judge
     d. Record verdict + reasoning
  3. Aggregate → JSON + Markdown report

Pre-requisite:
  - Backend running: .\\scripts\\start-backend.ps1
  - DB connected via UI or POST /v1/connections/connect
  - .env has OPENAI_API_KEY for judge LLM

Usage:
  python tests/eval/benchmark_runner.py --tag baseline
  python tests/eval/benchmark_runner.py --limit 5 --tag smoke
  python tests/eval/benchmark_runner.py --difficulty easy
  python tests/eval/benchmark_runner.py --dataset tests/eval/benchmark_dataset.yaml
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout on Windows so Unicode arrows / Vietnamese print correctly.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
import sqlalchemy
import yaml
from sqlalchemy import create_engine

# Project root path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from askdataai.config import settings  # noqa: E402
from askdataai.generation.llm_client import LLMClient  # noqa: E402

from tests.eval.canonical_hash import detect_order_matters, exec_match  # noqa: E402
from tests.eval.llm_judge import JudgeResult, judge  # noqa: E402
from tests.eval.sql_executor import ExecutionResult, execute_sql  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark")

DEFAULT_BACKEND = "http://localhost:8000"
DEFAULT_DATASET = ROOT / "tests" / "eval" / "benchmark_dataset.yaml"
BENCHMARKS_DIR = ROOT / "benchmarks"


# ─── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class BenchmarkExample:
    id: str
    question_vi: str
    question_en: str
    gold_sql: str
    difficulty: str
    tags: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class BenchmarkResult:
    example_id: str
    difficulty: str
    tags: list[str]

    # Pipeline output
    pred_sql: str = ""
    pred_translated: str = ""
    pred_rows: list[dict] = field(default_factory=list)
    pred_cols: list[str] = field(default_factory=list)
    pred_row_count: int = 0
    pred_valid: bool = False
    pred_error: str = ""
    pred_intent: str = ""
    pred_retries: int = 0

    # Gold execution
    gold_rows: list[dict] = field(default_factory=list)
    gold_cols: list[str] = field(default_factory=list)
    gold_row_count: int = 0
    gold_valid: bool = False
    gold_error: str = ""

    # Comparison
    match: bool = False
    match_method: str = ""           # "exact" | "llm_judge" | "skipped" | "error"
    judge_verdict: str = ""           # "correct" | "incorrect" | "partial" | ""
    judge_reasoning: str = ""
    judge_confidence: float = 0.0
    compare_reason: str = ""          # detail from exec_match (e.g., "row_count mismatch")

    # Timing
    pipeline_latency_ms: int = 0
    gold_latency_ms: int = 0
    judge_latency_ms: int = 0


@dataclass
class BenchmarkReport:
    metadata: dict
    config_snapshot: dict
    results: list[BenchmarkResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def correct_count(self) -> int:
        return sum(1 for r in self.results if r.match)

    @property
    def ex_match_rate(self) -> float:
        return self.correct_count / self.total if self.total else 0.0

    @property
    def valid_rate(self) -> float:
        return sum(1 for r in self.results if r.pred_valid) / self.total if self.total else 0.0

    def by_method(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for r in self.results:
            out[r.match_method or "none"] += 1
        return dict(out)

    def by_difficulty(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for diff in ("easy", "medium", "hard"):
            subset = [r for r in self.results if r.difficulty == diff]
            if subset:
                out[diff] = {
                    "n": len(subset),
                    "correct": sum(1 for r in subset if r.match),
                    "ex_rate": sum(1 for r in subset if r.match) / len(subset),
                    "valid_rate": sum(1 for r in subset if r.pred_valid) / len(subset),
                }
        return out

    def by_tag(self) -> dict[str, dict]:
        all_tags: set[str] = set()
        for r in self.results:
            all_tags.update(r.tags)
        out: dict[str, dict] = {}
        for tag in sorted(all_tags):
            subset = [r for r in self.results if tag in r.tags]
            if subset:
                out[tag] = {
                    "n": len(subset),
                    "ex_rate": sum(1 for r in subset if r.match) / len(subset),
                }
        return out

    def latency_p50(self) -> int:
        if not self.results:
            return 0
        sorted_lat = sorted(r.pipeline_latency_ms for r in self.results)
        return sorted_lat[len(sorted_lat) // 2]

    def latency_p95(self) -> int:
        if not self.results:
            return 0
        sorted_lat = sorted(r.pipeline_latency_ms for r in self.results)
        return sorted_lat[min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)]

    def to_json(self, path: Path) -> None:
        data = {
            "metadata": self.metadata,
            "config_snapshot": self.config_snapshot,
            "summary": {
                "total": self.total,
                "correct": self.correct_count,
                "ex_match_rate": round(self.ex_match_rate, 4),
                "valid_rate": round(self.valid_rate, 4),
                "by_method": self.by_method(),
                "by_difficulty": self.by_difficulty(),
                "by_tag": self.by_tag(),
                "latency_p50_ms": self.latency_p50(),
                "latency_p95_ms": self.latency_p95(),
            },
            "results": [asdict(r) for r in self.results],
        }
        path.write_text(
            json.dumps(data, default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ─── Loaders ─────────────────────────────────────────────────────────────


def load_dataset(path: Path) -> list[BenchmarkExample]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    examples = []
    for item in raw.get("examples", []):
        examples.append(BenchmarkExample(
            id=item["id"],
            question_vi=item["question_vi"],
            question_en=item.get("question_en", ""),
            gold_sql=item["gold_sql"],
            difficulty=item["difficulty"],
            tags=item.get("tags", []),
            notes=item.get("notes", ""),
        ))
    return examples


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


# ─── Backend interaction ─────────────────────────────────────────────────


def check_backend_health(backend_url: str) -> bool:
    try:
        r = httpx.get(f"{backend_url}/health", timeout=5)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Backend health check failed: {e}")
        return False


def check_backend_deployed(backend_url: str) -> tuple[bool, str]:
    try:
        r = httpx.get(f"{backend_url}/v1/connections/status", timeout=5)
        if r.status_code != 200:
            return False, f"status endpoint HTTP {r.status_code}"
        data = r.json()
        if data.get("connected") and data.get("deployed"):
            return True, ""
        return False, f"not deployed (connected={data.get('connected')}, deployed={data.get('deployed')})"
    except Exception as e:
        return False, str(e)


def ask_pipeline(backend_url: str, question_vi: str, sample_id: str) -> dict:
    """Call POST /v1/ask. Returns response dict; on failure returns dict with error key."""
    payload = {
        "question": question_vi,
        "session_id": f"bench-{sample_id}",
        "debug": True,
        "enable_voting": False,  # explicit — user opted out
    }
    try:
        r = httpx.post(
            f"{backend_url}/v1/ask",
            json=payload,
            timeout=120,  # generous for slow pipelines
        )
        if r.status_code != 200:
            return {"_http_error": f"HTTP {r.status_code}: {r.text[:200]}"}
        return r.json()
    except httpx.TimeoutException:
        return {"_http_error": "timeout (>120s)"}
    except Exception as e:
        return {"_http_error": f"{type(e).__name__}: {str(e)[:200]}"}


# ─── Per-example runner ──────────────────────────────────────────────────


def run_one(
    ex: BenchmarkExample,
    *,
    engine: sqlalchemy.Engine,
    backend_url: str,
    llm: LLMClient,
) -> BenchmarkResult:
    result = BenchmarkResult(
        example_id=ex.id,
        difficulty=ex.difficulty,
        tags=ex.tags,
    )

    # ── 1. Execute gold SQL ──────────────────────────────────────────
    gold_exec: ExecutionResult = execute_sql(engine, ex.gold_sql)
    result.gold_rows = gold_exec.rows
    result.gold_cols = gold_exec.columns
    result.gold_row_count = gold_exec.row_count
    result.gold_valid = gold_exec.success
    result.gold_error = gold_exec.error
    result.gold_latency_ms = gold_exec.duration_ms

    if not gold_exec.success:
        result.match = False
        result.match_method = "error"
        result.compare_reason = f"gold SQL failed: {gold_exec.error[:200]}"
        return result

    # ── 2. Send question to pipeline ─────────────────────────────────
    t0 = time.time()
    response = ask_pipeline(backend_url, ex.question_vi, ex.id)
    result.pipeline_latency_ms = int((time.time() - t0) * 1000)

    if "_http_error" in response:
        result.match = False
        result.match_method = "error"
        result.pred_error = response["_http_error"]
        result.compare_reason = f"pipeline call failed: {response['_http_error']}"
        return result

    result.pred_sql = response.get("sql", "")
    result.pred_rows = response.get("rows", []) or []
    result.pred_cols = response.get("columns", []) or []
    result.pred_row_count = response.get("row_count", 0)
    result.pred_valid = bool(response.get("valid", False))
    result.pred_error = response.get("error", "") or ""
    result.pred_intent = response.get("intent", "")
    result.pred_retries = int(response.get("retries", 0))
    pipeline_info = response.get("pipeline_info", {}) or {}
    result.pred_translated = pipeline_info.get("translated_question", "")

    if not result.pred_valid:
        # Pipeline returned but SQL invalid → automatically incorrect
        result.match = False
        result.match_method = "skipped"
        result.compare_reason = f"pipeline pred SQL invalid: {result.pred_error[:200]}"
        # Still ask LLM to be sure (intent might be GREETING/SCHEMA_EXPLORE etc.)
        # But for TEXT_TO_SQL with valid=false → just mark incorrect
        if result.pred_intent == "TEXT_TO_SQL":
            return result
        # For non-TEXT_TO_SQL intents, gold expects SQL → still incorrect
        return result

    # ── 3. Fast path: canonical exec_match ───────────────────────────
    order_matters = detect_order_matters(ex.gold_sql)
    matched, reason = exec_match(
        pred_rows=result.pred_rows,
        pred_cols=result.pred_cols,
        gold_rows=result.gold_rows,
        gold_cols=result.gold_cols,
        order_matters=order_matters,
    )
    result.compare_reason = reason

    if matched:
        result.match = True
        result.match_method = "exact"
        return result

    # ── 4. Fallback: LLM judge ───────────────────────────────────────
    t1 = time.time()
    jr: JudgeResult = judge(
        question_vi=ex.question_vi,
        question_en=ex.question_en,
        gold_sql=ex.gold_sql,
        pred_sql=result.pred_sql,
        gold_rows=result.gold_rows,
        gold_cols=result.gold_cols,
        gold_row_count=result.gold_row_count,
        pred_rows=result.pred_rows,
        pred_cols=result.pred_cols,
        pred_row_count=result.pred_row_count,
        pred_valid=result.pred_valid,
        pred_error=result.pred_error,
        llm=llm,
    )
    result.judge_latency_ms = int((time.time() - t1) * 1000)
    result.judge_verdict = jr.verdict
    result.judge_reasoning = jr.reasoning
    result.judge_confidence = jr.confidence
    result.match_method = "llm_judge"
    result.match = jr.verdict == "correct"

    return result


# ─── Main runner ─────────────────────────────────────────────────────────


def run_benchmark(
    examples: list[BenchmarkExample],
    *,
    backend_url: str,
    tag: str,
) -> BenchmarkReport:
    engine = create_engine(settings.connection_string)
    llm = LLMClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model="gpt-4o-mini",  # judge model — cheap, deterministic
    )

    config_snapshot = {
        "backend_url": backend_url,
        "judge_model": "gpt-4o-mini",
        "openai_base_url": settings.openai_base_url,
    }

    results: list[BenchmarkResult] = []
    for i, ex in enumerate(examples, 1):
        logger.info(f"[{i}/{len(examples)}] {ex.id} ({ex.difficulty}): {ex.question_vi[:70]}")
        try:
            r = run_one(ex, engine=engine, backend_url=backend_url, llm=llm)
        except Exception as e:
            logger.exception(f"Unhandled error on {ex.id}")
            r = BenchmarkResult(
                example_id=ex.id, difficulty=ex.difficulty, tags=ex.tags,
                match=False, match_method="error",
                compare_reason=f"unhandled: {type(e).__name__}: {e}",
            )
        results.append(r)

        # Live progress line
        verdict = "✓" if r.match else "✗"
        meta = r.match_method
        if r.match_method == "llm_judge":
            meta = f"llm:{r.judge_verdict}"
        logger.info(
            f"  {verdict} match={r.match} method={meta} "
            f"pred_rows={r.pred_row_count} gold_rows={r.gold_row_count} "
            f"latency={r.pipeline_latency_ms}ms"
        )

    return BenchmarkReport(
        metadata={
            "tag": tag,
            "git_sha": _git_sha(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "dataset_size": len(examples),
        },
        config_snapshot=config_snapshot,
        results=results,
    )


# ─── CLI ─────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend URL (default: http://localhost:8000)")
    p.add_argument("--tag", default="default", help="Run tag for output filename")
    p.add_argument("--limit", type=int, default=None, help="Run only first N samples (for smoke test)")
    p.add_argument("--difficulty", choices=["easy", "medium", "hard"], default=None)
    p.add_argument("--example-id", default=None, help="Run only one specific example by id")
    args = p.parse_args()

    # Pre-flight: backend up + deployed
    if not check_backend_health(args.backend):
        logger.error(f"Backend not responding at {args.backend}")
        logger.error("Start backend first: .\\scripts\\start-backend.ps1")
        return 2

    deployed, msg = check_backend_deployed(args.backend)
    if not deployed:
        logger.error(f"Backend not deployed: {msg}")
        logger.error("Connect DB first via UI or POST /v1/connections/connect")
        return 3

    # Load + filter dataset
    if not args.dataset.exists():
        logger.error(f"Dataset not found: {args.dataset}")
        return 4

    examples = load_dataset(args.dataset)
    if args.difficulty:
        examples = [e for e in examples if e.difficulty == args.difficulty]
    if args.example_id:
        examples = [e for e in examples if e.id == args.example_id]
    if args.limit:
        examples = examples[: args.limit]

    if not examples:
        logger.error("No examples after filters")
        return 5

    logger.info(f"Running benchmark: {len(examples)} examples, tag={args.tag}")

    # Run
    report = run_benchmark(examples, backend_url=args.backend, tag=args.tag)

    # Save
    BENCHMARKS_DIR.mkdir(exist_ok=True)
    out_file = BENCHMARKS_DIR / f"run_{report.metadata['git_sha']}_{report.metadata['timestamp'].replace(':', '-')}_{args.tag}.json"
    report.to_json(out_file)

    # Summary to console
    print("\n" + "=" * 60)
    print(f"Tag:              {args.tag}")
    print(f"Total:            {report.total}")
    print(f"Correct:          {report.correct_count}")
    print(f"EX match rate:    {report.ex_match_rate:.1%}")
    print(f"Valid SQL rate:   {report.valid_rate:.1%}")
    print(f"By method:        {report.by_method()}")
    print(f"By difficulty:    {report.by_difficulty()}")
    print(f"Latency p50:      {report.latency_p50()}ms")
    print(f"Latency p95:      {report.latency_p95()}ms")
    print(f"Saved to:         {out_file}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
