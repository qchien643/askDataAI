"""
Test script cho Phase 3: Indexing (WrenAI DDLChunker pattern).

Chạy: cd mini-wren-ai && .\\venv\\Scripts\\activate && python tests/test_indexing.py

Script này test:
1. HuggingFace embedder
2. ChromaDB create/delete collection
3. DDLChunker — verify TABLE + TABLE_COLUMNS chunks đúng format
4. TableDescriptionChunker — verify descriptions
5. Full index vào 2 collections
6. Search db_schema collection
7. Search table_descriptions collection
8. Hash-based skip + re-index
"""

import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import settings
from src.connectors.connection import SQLServerConnector
from src.connectors.schema_introspector import SchemaIntrospector
from src.modeling.manifest_builder import ManifestBuilder
from src.modeling.deploy import ManifestDeployer
from src.indexing.embedder import HuggingFaceEmbedder
from src.indexing.vector_store import VectorStore
from src.indexing.schema_indexer import (
    SchemaIndexer,
    DDLChunker,
    TableDescriptionChunker,
    COLLECTION_DB_SCHEMA,
    COLLECTION_TABLE_DESCRIPTIONS,
)


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_embedder():
    """Test 1: HuggingFace embedder."""
    separator("TEST 1: HuggingFace Embedder")

    embedder = HuggingFaceEmbedder(api_key=settings.huggingface_api_key)
    print(f"   Model: {embedder.model_name}")

    vec = embedder.embed_text("test embedding")
    print(f"   Dimensions: {len(vec)}")
    print(f"   Embedder working!")
    return embedder


def test_vector_store():
    """Test 2: ChromaDB operations."""
    separator("TEST 2: ChromaDB Vector Store")

    test_dir = os.path.join(os.path.dirname(__file__), "..", "chroma_test_data")
    store = VectorStore(persist_dir=test_dir)
    store.create_collection("test_col", recreate=True)
    assert store.count("test_col") == 0
    store.delete_collection("test_col")
    shutil.rmtree(test_dir, ignore_errors=True)
    print(f"   ChromaDB OK!")


def test_ddl_chunker():
    """Test 3: DDLChunker — verify chunk types."""
    separator("TEST 3: DDLChunker (TABLE + TABLE_COLUMNS)")

    connector = SQLServerConnector(settings.connection_string)
    introspector = SchemaIntrospector(connector.engine)
    config_path = os.path.join(os.path.dirname(__file__), "..", "models.yaml")
    builder = ManifestBuilder(config_path=config_path, introspector=introspector)
    manifest = builder.build()

    chunker = DDLChunker(column_batch_size=50)
    chunks = chunker.chunk(manifest)

    # Count by type
    table_chunks = [c for c in chunks if c["metadata"]["chunk_type"] == "TABLE"]
    col_chunks = [c for c in chunks if c["metadata"]["chunk_type"] == "TABLE_COLUMNS"]

    print(f"   Total chunks: {len(chunks)}")
    print(f"   TABLE chunks: {len(table_chunks)} (1 per model)")
    print(f"   TABLE_COLUMNS batches: {len(col_chunks)}")
    print()

    # Show first TABLE chunk
    first_table = table_chunks[0]
    print(f"   Example TABLE chunk ({first_table['metadata']['name']}):")
    print(f"   Content: {first_table['content'][:120]}...")
    print()

    # Show first TABLE_COLUMNS chunk
    first_cols = col_chunks[0]
    print(f"   Example TABLE_COLUMNS chunk ({first_cols['metadata']['name']}):")
    print(f"   Columns in batch: {first_cols['metadata']['column_count']}")
    print(f"   Content: {first_cols['content'][:150]}...")

    # Verify: mỗi model phải có ít nhất 1 TABLE + 1 TABLE_COLUMNS
    assert len(table_chunks) == len(manifest.models), \
        f"Expected {len(manifest.models)} TABLE chunks, got {len(table_chunks)}"

    # Check FK in TABLE_COLUMNS
    fk_count = 0
    for chunk in col_chunks:
        if "FOREIGN_KEY" in chunk["content"]:
            fk_count += 1
    print(f"\n   TABLE_COLUMNS batches with FK: {fk_count}")

    connector.close()
    return manifest


def test_table_description_chunker(manifest):
    """Test 4: TableDescriptionChunker."""
    separator("TEST 4: TableDescriptionChunker")

    chunker = TableDescriptionChunker()
    chunks = chunker.chunk(manifest)

    print(f"   Total description chunks: {len(chunks)} (1 per model)")
    for c in chunks[:3]:
        print(f"   - {c['metadata']['name']}: {c['content'][:80]}...")

    assert len(chunks) == len(manifest.models)
    print(f"   TableDescriptionChunker OK!")
    return chunks


def test_full_index(embedder, manifest):
    """Test 5: Full index vào 2 collections."""
    separator("TEST 5: Full Index (2 collections)")

    chroma_dir = os.path.join(os.path.dirname(__file__), "..", "chroma_data")
    store = VectorStore(persist_dir=chroma_dir)
    indexer = SchemaIndexer(vector_store=store, embedder=embedder)

    # Deploy to get hash
    manifests_dir = os.path.join(os.path.dirname(__file__), "..", "manifests")
    deployer = ManifestDeployer(manifests_dir=manifests_dir)
    deploy_result = deployer.deploy(manifest)

    print(f"   Indexing {len(manifest.models)} models into 2 collections...")
    result = indexer.index(
        manifest=manifest,
        manifest_hash=deploy_result.manifest_hash,
        force=True,
    )

    print(f"   Indexed: {result['indexed']}")
    print(f"   db_schema docs: {result['db_schema_docs']}")
    print(f"   table_description docs: {result['table_desc_docs']}")

    assert result["indexed"]
    assert result["db_schema_docs"] > len(manifest.models), \
        "db_schema should have more docs than models (TABLE + TABLE_COLUMNS)"
    assert result["table_desc_docs"] == len(manifest.models), \
        "table_descriptions should have exactly 1 doc per model"

    return indexer, deploy_result


def test_search_schema(indexer):
    """Test 6: Search db_schema collection."""
    separator("TEST 6: Search db_schema (TABLE + TABLE_COLUMNS)")

    queries = [
        ("SalesAmount revenue", "internet_sales"),
        ("CustomerKey foreign key", "customers"),
        ("ProductKey product name", "products"),
    ]

    for query, expected in queries:
        results = indexer.search_schema(query, top_k=3)
        names = [r["metadata"]["name"] for r in results]
        found = expected in names
        status = "OK" if found else "MISS"
        print(f"   [{status}] \"{query}\" -> {names}")


def test_search_descriptions(indexer):
    """Test 7: Search table_descriptions collection."""
    separator("TEST 7: Search table_descriptions")

    queries = [
        ("customer information", "customers"),
        ("product categories", "product_categories"),
        ("sales region territory", "sales_territory"),
        ("promotion discount", "promotions"),
    ]

    passed = 0
    for query, expected in queries:
        results = indexer.search_descriptions(query, top_k=3)
        names = [r["metadata"]["name"] for r in results]
        found = expected in names
        if found:
            passed += 1
        status = "OK" if found else "MISS"
        print(f"   [{status}] \"{query}\" -> {names}")

    print(f"\n   Results: {passed}/{len(queries)} queries matched in top 3")


def test_hash_skip_and_reindex(indexer, manifest, deploy_result):
    """Test 8: Hash skip + re-index."""
    separator("TEST 8: Hash skip + re-index")

    # Skip
    result = indexer.index(manifest=manifest, manifest_hash=deploy_result.manifest_hash)
    print(f"   Same hash -> indexed: {result['indexed']}, reason: {result['reason']}")
    assert not result["indexed"]

    # Re-index with different hash
    result = indexer.index(manifest=manifest, manifest_hash="new_hash_12345")
    print(f"   New hash  -> indexed: {result['indexed']}, reason: {result['reason']}")
    assert result["indexed"]

    print(f"   Hash-based skip + re-index OK!")


def main():
    print("=" * 60)
    print("  Mini Wren AI - Phase 3: Indexing Test (DDLChunker)")
    print("=" * 60)

    embedder = test_embedder()
    test_vector_store()
    manifest = test_ddl_chunker()
    test_table_description_chunker(manifest)
    indexer, deploy_result = test_full_index(embedder, manifest)
    test_search_schema(indexer)
    test_search_descriptions(indexer)
    test_hash_skip_and_reindex(indexer, manifest, deploy_result)

    separator("ALL TESTS PASSED")
    print("Phase 3: Indexing (DDLChunker pattern) is ready!\n")


if __name__ == "__main__":
    main()
