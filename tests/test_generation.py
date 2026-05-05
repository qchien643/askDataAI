"""
Test script cho Phase 5: SQL Generation + Correction.

Chay: cd mini-wren-ai && .\\venv\\Scripts\\activate && python tests/test_generation.py

Tests:
1. Intent classifier: data question -> TEXT_TO_SQL
2. Intent classifier: general question -> GENERAL
3. SQL Rewriter: model names -> DB names
4. SQL Generation: cau hoi -> SQL (model names)
5-9. End-to-end: question -> intent -> retrieve -> generate -> rewrite -> correct -> results
"""

import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")

from askdataai.config import settings
from askdataai.connectors.connection import SQLServerConnector
from askdataai.connectors.schema_introspector import SchemaIntrospector
from askdataai.modeling.manifest_builder import ManifestBuilder
from askdataai.modeling.deploy import ManifestDeployer
from askdataai.indexing.embedder import OpenAIEmbedder
from askdataai.indexing.vector_store import VectorStore
from askdataai.indexing.schema_indexer import SchemaIndexer
from askdataai.retrieval.schema_retriever import SchemaRetriever
from askdataai.retrieval.context_builder import ContextBuilder
from askdataai.generation.llm_client import LLMClient
from askdataai.generation.intent_classifier import IntentClassifier, Intent
from askdataai.generation.sql_generator import SQLGenerator
from askdataai.generation.sql_rewriter import SQLRewriter
from askdataai.generation.sql_corrector import SQLCorrector


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def setup():
    """Setup toan bo pipeline."""
    separator("SETUP")

    connector = SQLServerConnector(settings.connection_string)
    introspector = SchemaIntrospector(connector.engine)
    config_path = os.path.join(os.path.dirname(__file__), "..", "models.yaml")
    manifest = ManifestBuilder(config_path=config_path, introspector=introspector).build()

    chroma_dir = os.path.join(os.path.dirname(__file__), "..", "chroma_data")
    store = VectorStore(persist_dir=chroma_dir)
    embedder = OpenAIEmbedder(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    indexer = SchemaIndexer(vector_store=store, embedder=embedder)

    deployer = ManifestDeployer(
        manifests_dir=os.path.join(os.path.dirname(__file__), "..", "manifests"))
    deploy_result = deployer.deploy(manifest)
    indexer.index(manifest=manifest, manifest_hash=deploy_result.manifest_hash)

    retriever = SchemaRetriever(indexer, manifest)
    context_builder = ContextBuilder(manifest)
    llm = LLMClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    classifier = IntentClassifier(llm)
    generator = SQLGenerator(llm)
    rewriter = SQLRewriter(manifest)
    corrector = SQLCorrector(llm, rewriter, connector.engine)

    print("   Setup OK")
    return {
        "connector": connector,
        "manifest": manifest,
        "retriever": retriever,
        "context_builder": context_builder,
        "llm": llm,
        "classifier": classifier,
        "generator": generator,
        "rewriter": rewriter,
        "corrector": corrector,
    }


def test_intent_text_to_sql(ctx):
    separator("TEST 1: Intent - TEXT_TO_SQL")
    model_names = [m.name for m in ctx["manifest"].models]
    result = ctx["classifier"].classify("Tong doanh thu theo thang", model_names)
    print(f"   Intent: {result.intent.value}")
    print(f"   Reason: {result.reason}")
    assert result.intent == Intent.TEXT_TO_SQL, f"Expected TEXT_TO_SQL, got {result.intent}"
    print("   OK!")


def test_intent_general(ctx):
    separator("TEST 2: Intent - GENERAL")
    model_names = [m.name for m in ctx["manifest"].models]
    result = ctx["classifier"].classify("Ban la ai?", model_names)
    print(f"   Intent: {result.intent.value}")
    print(f"   Reason: {result.reason}")
    assert result.intent == Intent.GENERAL, f"Expected GENERAL, got {result.intent}"
    print("   OK!")


def test_rewriter(ctx):
    separator("TEST 3: SQL Rewriter")
    test_sql = (
        "SELECT customers.FirstName, SUM(internet_sales.SalesAmount) "
        "FROM internet_sales "
        "JOIN customers ON internet_sales.CustomerKey = customers.CustomerKey "
        "GROUP BY customers.FirstName"
    )
    rewritten = ctx["rewriter"].rewrite(test_sql)
    print(f"   Input:    {test_sql[:80]}...")
    print(f"   Rewritten: {rewritten[:80]}...")

    assert "DimCustomer" in rewritten, "Should rewrite customers -> DimCustomer"
    assert "FactInternetSales" in rewritten, "Should rewrite internet_sales -> FactInternetSales"

    mapping = ctx["rewriter"].get_mapping()
    print(f"   Mappings ({len(mapping)}):")
    for m, t in list(mapping.items())[:3]:
        print(f"     {m} -> {t}")
    print("   OK!")


def test_generate_sql(ctx):
    separator("TEST 4: SQL Generation")
    question = "Tong doanh thu internet sales"

    retrieval = ctx["retriever"].retrieve(question)
    ddl = ctx["context_builder"].build(retrieval.db_schemas, retrieval.model_names)
    result = ctx["generator"].generate(question, ddl)

    print(f"   Question:    {question}")
    print(f"   SQL:         {result.sql}")
    print(f"   Explanation: {result.explanation}")

    assert result.sql, "Should generate SQL"
    print("   OK!")


def test_end_to_end(ctx, question):
    """
    Full pipeline: question -> intent -> retrieve -> generate -> rewrite -> correct.
    In ra SQL va ket qua de verify semantic correctness.
    """
    model_names = [m.name for m in ctx["manifest"].models]

    # 1. Intent
    intent_result = ctx["classifier"].classify(question, model_names)
    if intent_result.intent != Intent.TEXT_TO_SQL:
        print(f"   Intent: {intent_result.intent.value} (skip SQL)")
        return None

    # 2. Retrieve
    retrieval = ctx["retriever"].retrieve(question)
    ddl = ctx["context_builder"].build(retrieval.db_schemas, retrieval.model_names)

    # 3. Generate SQL (model names)
    gen_result = ctx["generator"].generate(question, ddl)
    print(f"   SQL (model names):")
    for line in gen_result.sql.strip().split("\n"):
        print(f"     {line}")

    # 4. Rewrite SQL (DB names) - hien thi de verify mapping
    rewritten = ctx["rewriter"].rewrite(gen_result.sql)
    print(f"   SQL (DB names):")
    for line in rewritten.strip().split("\n"):
        print(f"     {line}")

    # 5. Correct (execute on DB + retry if error)
    correction = ctx["corrector"].validate_and_correct(
        sql=gen_result.sql,
        ddl_context=ddl,
        question=question,
        explanation=gen_result.explanation,
    )

    print(f"   Explanation: {gen_result.explanation}")
    print(f"   Valid: {correction.valid}, Retries: {correction.retries}")

    # 6. Hien thi ket qua thuc te de verify semantic
    if correction.valid and correction.result:
        rows = correction.result.get("rows", [])
        cols = correction.result.get("columns", [])
        print(f"   Columns: {cols}")
        print(f"   Results ({len(rows)} rows):")
        for row in rows[:5]:
            print(f"     {row}")
        if len(rows) > 5:
            print(f"     ... ({len(rows) - 5} more rows)")
    if correction.errors:
        for i, err in enumerate(correction.errors):
            print(f"   Error {i+1}: {err[:150]}")

    return correction


def main():
    print("=" * 60)
    print("  Mini Wren AI - Phase 5: SQL Generation Test")
    print("=" * 60)

    ctx = setup()

    # === Unit tests ===
    # test_intent_text_to_sql(ctx)
    # test_intent_general(ctx)
    # test_rewriter(ctx)
    # test_generate_sql(ctx)

    # === End-to-end tests ===
    # Moi cau hoi in ra SQL + ket qua thuc te de verify semantic correctness
    questions = [
        "Tong doanh thu internet sales",
        # "Top 5 san pham ban chay nhat",
        # "So luong khach hang theo quoc gia",
        # "Doanh thu theo thang nam 2013",
        # "San pham nao co gia niem yet cao nhat",
    ]

    passed = 0
    results_summary = []
    for i, q in enumerate(questions, 5):
        separator(f"TEST {i}: End-to-end")
        print(f"   Question: {q}")
        r = test_end_to_end(ctx, q)
        if r and r.valid:
            passed += 1
            results_summary.append(("OK", q))
        else:
            results_summary.append(("FAIL", q))

    # === Summary ===
    separator("SUMMARY")
    print(f"   End-to-end: {passed}/{len(questions)} questions passed")
    for status, q in results_summary:
        print(f"   [{status}] {q}")

    ctx["connector"].close()

    separator("ALL TESTS COMPLETED")
    print(f"Phase 5: SQL Generation + Correction ready!")
    print(f"End-to-end success rate: {passed}/{len(questions)}\n")


if __name__ == "__main__":
    main()
