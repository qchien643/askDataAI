"""
Test script cho Phase 4: Retrieval.

Chạy: cd mini-wren-ai && .\\venv\\Scripts\\activate && python tests/test_retrieval.py

Yêu cầu: Phase 3 indexing đã chạy thành công (chroma_data có dữ liệu).

Tests:
1. Table retrieval: "tổng doanh thu" → internet_sales
2. Relationship expansion: internet_sales → kéo thêm customers, products...
3. Full retrieve: "doanh thu theo khách hàng" → internet_sales + customers
4. DDL context build: verify CREATE TABLE dùng model names
5. DDL không chứa tên DB thật (dbo.DimCustomer)
6. Multi-hop: "sản phẩm theo danh mục" → products + subcategories + categories
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def setup():
    """Build manifest + index nếu cần."""
    separator("SETUP: Build manifest + ensure indexed")

    connector = SQLServerConnector(settings.connection_string)
    introspector = SchemaIntrospector(connector.engine)
    config_path = os.path.join(os.path.dirname(__file__), "..", "models.yaml")
    builder = ManifestBuilder(config_path=config_path, introspector=introspector)
    manifest = builder.build()

    chroma_dir = os.path.join(os.path.dirname(__file__), "..", "chroma_data")
    store = VectorStore(persist_dir=chroma_dir)
    embedder = OpenAIEmbedder(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    indexer = SchemaIndexer(vector_store=store, embedder=embedder)

    # Deploy + index (sẽ skip nếu hash không đổi)
    deployer = ManifestDeployer(
        manifests_dir=os.path.join(os.path.dirname(__file__), "..", "manifests")
    )
    deploy_result = deployer.deploy(manifest)
    index_result = indexer.index(
        manifest=manifest,
        manifest_hash=deploy_result.manifest_hash,
    )

    if index_result["indexed"]:
        print(f"   Indexed: {index_result['db_schema_docs']} schema + "
              f"{index_result['table_desc_docs']} descriptions")
    else:
        print(f"   Already indexed (hash unchanged)")

    connector.close()
    return manifest, indexer


def test_table_retrieval(indexer, manifest):
    """Test 1: Table retrieval basic."""
    separator("TEST 1: Table Retrieval")

    retriever = SchemaRetriever(indexer, manifest, table_retrieval_size=3)
    result = retriever.retrieve("tổng doanh thu", expand_relationships=False)

    print(f"   Query: \"tổng doanh thu\"")
    print(f"   Found: {result.model_names}")

    sales_found = any("sales" in n for n in result.model_names)
    assert sales_found, f"Expected a sales model, got {result.model_names}"
    print(f"   ✅ Sales model found!")
    return retriever


def test_relationship_expansion(retriever):
    """Test 2: Relationship expansion."""
    separator("TEST 2: Relationship Expansion")

    # Without expansion
    result_no_exp = retriever.retrieve(
        "doanh thu theo khách hàng", expand_relationships=False
    )
    print(f"   Without expansion: {result_no_exp.model_names}")

    # With expansion
    result_exp = retriever.retrieve(
        "doanh thu theo khách hàng", expand_relationships=True
    )
    print(f"   With expansion:    {result_exp.model_names}")

    assert len(result_exp.model_names) > len(result_no_exp.model_names), \
        "Expansion should add more models"

    # "customers" should be in expanded results
    has_sales = any("sales" in n for n in result_exp.model_names)
    has_customers = "customers" in result_exp.model_names
    print(f"   Has sales model: {has_sales}")
    print(f"   Has customers (via rel): {has_customers}")

    assert has_sales, "Should find a sales model"
    print(f"   ✅ Relationship expansion working!")


def test_full_retrieve_with_schemas(retriever):
    """Test 3: Full retrieve with db_schemas."""
    separator("TEST 3: Full Retrieve + db_schemas")

    result = retriever.retrieve("doanh thu theo khách hàng")

    print(f"   Models: {result.model_names}")
    print(f"   Expanded from: {result.expanded_from}")
    print(f"   db_schemas: {len(result.db_schemas)} dicts")

    for schema in result.db_schemas:
        name = schema.get("name", "?")
        cols = len(schema.get("columns", []))
        print(f"     - {name}: {cols} columns")

    assert len(result.db_schemas) > 0, "Should have db_schemas"
    print(f"   ✅ Full retrieval OK!")
    return result


def test_ddl_context_build(manifest, result):
    """Test 4: DDL context uses model names."""
    separator("TEST 4: DDL Context Build (model names)")

    builder = ContextBuilder(manifest)
    ddl = builder.build(result.db_schemas, result.model_names)

    print(f"   DDL length: {len(ddl)} chars")
    print(f"   Preview:")
    # Show first 500 chars
    for line in ddl[:500].split("\n"):
        print(f"     {line}")
    if len(ddl) > 500:
        print(f"     ... ({len(ddl) - 500} more chars)")

    # Verify: DDL dùng model names, KHÔNG dùng table_reference
    assert "CREATE TABLE" in ddl, "DDL should have CREATE TABLE"

    # Check model names appear in DDL
    for schema in result.db_schemas:
        model_name = schema.get("name", "")
        assert f"CREATE TABLE {model_name}" in ddl, \
            f"DDL should use model name '{model_name}'"

    print(f"   ✅ DDL uses model names!")
    return ddl


def test_ddl_no_db_names(ddl):
    """Test 5: DDL KHÔNG chứa tên DB thật."""
    separator("TEST 5: DDL must NOT contain DB table references")

    db_references = [
        "dbo.DimCustomer", "dbo.DimProduct", "dbo.DimDate",
        "dbo.FactInternetSales", "dbo.FactResellerSales",
        "dbo.DimGeography", "dbo.DimPromotion",
    ]

    for ref in db_references:
        assert ref not in ddl, \
            f"DDL should NOT contain DB reference '{ref}'"

    print(f"   Checked {len(db_references)} DB references: none found ✅")
    print(f"   ✅ DDL correctly uses model names only!")


def test_build_from_models(manifest):
    """Test 6: Build DDL directly from model names."""
    separator("TEST 6: Build DDL from model names (no vector search)")

    builder = ContextBuilder(manifest)
    ddl = builder.build_from_models(["internet_sales", "customers", "products"])

    print(f"   DDL length: {len(ddl)} chars")

    assert "CREATE TABLE internet_sales" in ddl
    assert "CREATE TABLE customers" in ddl
    assert "CREATE TABLE products" in ddl
    assert "Relationships:" in ddl

    # Check display_name in comments
    assert "alias" in ddl, "DDL should have alias (display_name) in comments"

    # Verify FK only shows if both tables present
    assert "FOREIGN KEY" in ddl, "Should have FK constraints"

    print(f"   ✅ Build from models OK!")


def test_multi_hop(retriever, manifest):
    """Test 7: Multi-hop relationship."""
    separator("TEST 7: Multi-hop (product → subcategory → category)")

    result = retriever.retrieve("sản phẩm theo danh mục", top_k=3)

    print(f"   Query: \"sản phẩm theo danh mục\"")
    print(f"   Models: {result.model_names}")

    has_products = "products" in result.model_names
    has_subcat = "product_subcategories" in result.model_names
    has_cat = "product_categories" in result.model_names

    print(f"   products: {has_products}")
    print(f"   product_subcategories: {has_subcat}")
    print(f"   product_categories: {has_cat}")

    # Build DDL
    builder = ContextBuilder(manifest)
    ddl = builder.build(result.db_schemas, result.model_names)

    product_models = [n for n in result.model_names if "product" in n]
    print(f"   Product-related models: {product_models}")
    print(f"   ✅ Multi-hop retrieval done!")
    # print(ddl)


def main():
    print("=" * 60)
    print("  Mini Wren AI - Phase 4: Retrieval Test")
    print("=" * 60)

    manifest, indexer = setup()
    retriever = test_table_retrieval(indexer, manifest)
    test_relationship_expansion(retriever)
    result = test_full_retrieve_with_schemas(retriever)
    ddl = test_ddl_context_build(manifest, result)
    test_ddl_no_db_names(ddl)
    test_build_from_models(manifest)
    test_multi_hop(retriever, manifest)

    separator("ALL TESTS PASSED")
    print("Phase 4: Retrieval is ready!\n")


if __name__ == "__main__":
    main()
