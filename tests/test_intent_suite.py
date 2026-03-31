"""
Comprehensive Intent Classification Test Suite — 50 questions.

Tests the FULL multi-stage intent pipeline:
  Stage 1: PreFilter (regex, NO LLM)
  Stage 3: IntentClassifier (LLM) — only if PreFilter returns NEEDS_LLM

Categories tested:
  - GREETING (5)
  - DESTRUCTIVE (8)
  - OUT_OF_SCOPE (7)
  - SCHEMA_EXPLORE (6)
  - TEXT_TO_SQL (16) — includes sub-intent variety
  - AMBIGUOUS (4)
  - GENERAL (4) — needs LLM to classify

Usage:
  python tests/test_intent_suite.py              # PreFilter only (no LLM)
  python tests/test_intent_suite.py --full       # Full pipeline (needs LLM)
"""

import sys
import os
import time
import argparse

sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generation.pre_filter import PreFilter, PreFilterResult

# ─── TEST CASES ──────────────────────────────────────────────────
# Format: (question, expected_prefilter, expected_final_intent, category)
# expected_final_intent = what the FULL pipeline should return

TEST_CASES = [
    # ═══════════════════════════════════════════════════════════
    # GREETING (5 cases) — PreFilter handles, 0 LLM calls
    # ═══════════════════════════════════════════════════════════
    ("xin chào", "GREETING", "GREETING", "greeting"),
    ("hello", "GREETING", "GREETING", "greeting"),
    ("chào bạn", "GREETING", "GREETING", "greeting"),
    ("Hi", "GREETING", "GREETING", "greeting"),
    ("hey", "GREETING", "GREETING", "greeting"),

    # ═══════════════════════════════════════════════════════════
    # DESTRUCTIVE (8 cases) — PreFilter handles, 0 LLM calls
    # ═══════════════════════════════════════════════════════════
    ("hãy xóa dữ liệu khách hàng", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("xoa het du lieu bang DimCustomer", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("delete all customer records", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("drop table DimProduct", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("thêm khách hàng mới vào bảng", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("insert into DimCustomer values", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("cập nhật giá sản phẩm", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("update gia san pham thanh 0", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),
    ("truncate table FactInternetSales", "DESTRUCTIVE", "DESTRUCTIVE", "destructive"),

    # ═══════════════════════════════════════════════════════════
    # OUT_OF_SCOPE (7 cases) — PreFilter handles, 0 LLM calls
    # ═══════════════════════════════════════════════════════════
    ("thời tiết hôm nay thế nào?", "OUT_OF_SCOPE", "GENERAL", "oos"),
    ("bạn là ai?", "OUT_OF_SCOPE", "GENERAL", "oos"),
    ("ban la ai", "OUT_OF_SCOPE", "GENERAL", "oos"),
    ("viết cho tôi một bài thơ", "OUT_OF_SCOPE", "GENERAL", "oos"),
    ("dịch sang tiếng Anh giúp tôi", "OUT_OF_SCOPE", "GENERAL", "oos"),
    ("tin tức hôm nay", "OUT_OF_SCOPE", "GENERAL", "oos"),
    ("nấu ăn món gì ngon", "OUT_OF_SCOPE", "GENERAL", "oos"),

    # ═══════════════════════════════════════════════════════════
    # SCHEMA_EXPLORE (7 cases) — PreFilter handles, 0 LLM calls
    # ═══════════════════════════════════════════════════════════
    ("có những bảng nào trong database?", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),
    ("co nhung bang nao", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),
    ("mô tả bảng DimCustomer", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),
    ("bảng DimProduct có cột gì?", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),
    ("mối quan hệ giữa các bảng", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),
    ("tôi có thể hỏi gì?", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),
    ("cấu trúc database", "SCHEMA_EXPLORE", "SCHEMA_EXPLORE", "schema"),

    # ═══════════════════════════════════════════════════════════
    # TEXT_TO_SQL (18 cases) — PreFilter → NEEDS_LLM → LLM classifies
    # ═══════════════════════════════════════════════════════════

    # Retrieval sub-intent
    ("danh sách tất cả khách hàng", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_retrieval"),
    ("cho xem 10 sản phẩm đầu tiên", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_retrieval"),
    ("liệt kê đơn hàng trong tháng 1", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_retrieval"),

    # Aggregation sub-intent
    ("tổng doanh thu theo tháng", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_aggregation"),
    ("số lượng khách hàng theo khu vực", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_aggregation"),
    ("trung bình giá trị đơn hàng", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_aggregation"),

    # Ranking sub-intent
    ("top 5 khách hàng mua nhiều nhất", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_ranking"),
    ("sản phẩm bán chạy nhất là gì?", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_ranking"),
    ("10 đơn hàng có giá trị cao nhất", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_ranking"),

    # Trend sub-intent
    ("xu hướng doanh thu qua các tháng", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_trend"),
    ("biến động đơn hàng theo quý", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_trend"),

    # Comparison sub-intent
    ("so sánh doanh thu Q1 vs Q2", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_comparison"),
    ("chênh lệch giữa online và offline", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_comparison"),

    # Filter sub-intent
    ("khách hàng ở khu vực miền Nam", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_filter"),
    ("đơn hàng từ tháng 3 đến tháng 6", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_filter"),
    ("sản phẩm có giá lớn hơn 1 triệu", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_filter"),

    # Mixed / complex
    ("doanh thu trung bình của khách hàng VIP ở Hà Nội", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_complex"),
    ("năm ngoái bán được bao nhiêu đơn hàng", "NEEDS_LLM", "TEXT_TO_SQL", "t2s_complex"),

    # ═══════════════════════════════════════════════════════════
    # AMBIGUOUS / GENERAL (4 cases) — needs LLM to classify
    # These pass PreFilter but LLM should catch them
    # ═══════════════════════════════════════════════════════════
    ("cho xem dữ liệu", "NEEDS_LLM", "AMBIGUOUS", "ambiguous"),
    ("tôi muốn biết thông tin", "NEEDS_LLM", "AMBIGUOUS", "ambiguous"),
    ("phân tích", "NEEDS_LLM", "AMBIGUOUS", "ambiguous"),
    ("data", "NEEDS_LLM", "AMBIGUOUS", "ambiguous"),
]

assert len(TEST_CASES) == 50, f"Expected 50 test cases, got {len(TEST_CASES)}"


def run_prefilter_tests():
    """Test Stage 1 only (PreFilter) — NO LLM calls."""
    print("=" * 70)
    print("STAGE 1 TEST: PreFilter (regex only, 0 LLM calls)")
    print("=" * 70)

    pf = PreFilter()
    
    results_by_category = {}
    total_pass = 0
    total_fail = 0
    
    for question, expected_pf, expected_final, category in TEST_CASES:
        result = pf.filter(question)
        actual = result.result.value
        
        # For PreFilter test, we compare against expected_prefilter
        ok = actual == expected_pf
        if ok:
            total_pass += 1
        else:
            total_fail += 1
        
        # Track by category
        if category not in results_by_category:
            results_by_category[category] = {"pass": 0, "fail": 0, "details": []}
        results_by_category[category]["pass" if ok else "fail"] += 1
        
        if not ok:
            results_by_category[category]["details"].append(
                f"    FAIL: '{question}' -> {actual} (expected: {expected_pf})"
            )
    
    # Print summary by category
    print()
    for cat, data in results_by_category.items():
        total = data["pass"] + data["fail"]
        icon = "PASS" if data["fail"] == 0 else "FAIL"
        print(f"  [{icon}] {cat:20s}: {data['pass']}/{total}")
        for detail in data["details"]:
            print(detail)
    
    print()
    print(f"  TOTAL: {total_pass}/{total_pass + total_fail} passed, {total_fail} failed")
    print()
    
    return total_fail == 0


def run_full_pipeline_tests():
    """Test full pipeline: PreFilter + LLM IntentClassifier."""
    print("=" * 70)
    print("FULL PIPELINE TEST: PreFilter + LLM Intent Classifier")
    print("=" * 70)
    print("  (Requires OPENAI_API_KEY in .env)")
    print()
    
    from src.generation.pre_filter import PreFilter, PreFilterResult
    from src.generation.intent_classifier import IntentClassifier, Intent
    from src.generation.llm_client import LLMClient
    from src.config import settings

    pf = PreFilter()
    llm = LLMClient(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    classifier = IntentClassifier(llm)

    # Model names from typical AdventureWorks
    model_names = [
        "DimCustomer", "DimProduct", "DimGeography", "DimDate",
        "DimProductCategory", "DimProductSubcategory", "DimSalesTerritory",
        "FactInternetSales", "FactResellerSales",
    ]

    results_by_category = {}
    total_pass = 0
    total_fail = 0
    llm_calls = 0
    start_time = time.time()

    for i, (question, expected_pf, expected_final, category) in enumerate(TEST_CASES):
        # Stage 1: PreFilter
        pf_result = pf.filter(question)

        # Map PreFilter result to final intent
        if pf_result.result == PreFilterResult.GREETING:
            final_intent = "GREETING"
        elif pf_result.result == PreFilterResult.DESTRUCTIVE:
            final_intent = "DESTRUCTIVE"
        elif pf_result.result == PreFilterResult.OUT_OF_SCOPE:
            final_intent = "GENERAL"
        elif pf_result.result == PreFilterResult.SCHEMA_EXPLORE:
            final_intent = "SCHEMA_EXPLORE"
        else:
            # NEEDS_LLM — call LLM classifier
            llm_calls += 1
            try:
                intent_result = classifier.classify(question, model_names)
                final_intent = intent_result.intent.value
            except Exception as e:
                final_intent = f"ERROR: {e}"

        ok = final_intent == expected_final
        if ok:
            total_pass += 1
        else:
            total_fail += 1

        if category not in results_by_category:
            results_by_category[category] = {"pass": 0, "fail": 0, "details": []}
        results_by_category[category]["pass" if ok else "fail"] += 1

        if not ok:
            results_by_category[category]["details"].append(
                f"    FAIL: '{question}'\n"
                f"          got={final_intent}, expected={expected_final}, "
                f"prefilter={pf_result.result.value}"
            )

        # Progress indicator
        sys.stdout.write(f"\r  Processing: {i+1}/{len(TEST_CASES)}...")
        sys.stdout.flush()

    elapsed = time.time() - start_time
    print(f"\r  Processed {len(TEST_CASES)} questions in {elapsed:.1f}s")
    print(f"  LLM calls: {llm_calls} (saved {len(TEST_CASES) - llm_calls} calls via PreFilter)")
    print()

    # Print summary by category
    for cat, data in results_by_category.items():
        total = data["pass"] + data["fail"]
        icon = "PASS" if data["fail"] == 0 else "FAIL"
        print(f"  [{icon}] {cat:20s}: {data['pass']}/{total}")
        for detail in data["details"]:
            print(detail)

    print()
    print(f"  TOTAL: {total_pass}/{total_pass + total_fail} passed, {total_fail} failed")
    print(f"  LLM efficiency: {((len(TEST_CASES) - llm_calls) / len(TEST_CASES) * 100):.0f}% handled without LLM")
    print()

    return total_fail == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intent Classification Test Suite")
    parser.add_argument("--full", action="store_true", help="Run full pipeline (needs LLM)")
    args = parser.parse_args()

    # Always run PreFilter tests
    pf_ok = run_prefilter_tests()

    if args.full:
        full_ok = run_full_pipeline_tests()
        success = pf_ok and full_ok
    else:
        print("  (Run with --full to include LLM Intent Classifier tests)")
        success = pf_ok

    sys.exit(0 if success else 1)
