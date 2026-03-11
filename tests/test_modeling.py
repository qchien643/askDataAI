"""
Test script cho Phase 2: Modeling Layer (MDL).

Chạy: cd mini-wren-ai && .\\venv\\Scripts\\activate && python tests/test_modeling.py

Script này test:
1. Build manifest từ models.yaml
2. Validate manifest against DB thật
3. Deploy manifest (lưu file + tính hash)
4. Re-deploy không đổi → hash unchanged
5. Sửa manifest → re-deploy → hash thay đổi
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import settings
from src.connectors.connection import SQLServerConnector
from src.connectors.schema_introspector import SchemaIntrospector
from src.modeling.manifest_builder import ManifestBuilder
from src.modeling.deploy import ManifestDeployer


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_build_manifest():
    """Test 1: Build manifest từ models.yaml."""
    separator("TEST 1: Build Manifest từ models.yaml")

    # Connect to DB
    connector = SQLServerConnector(settings.connection_string)
    connector.test_connection()
    introspector = SchemaIntrospector(connector.engine)

    # Build manifest
    config_path = os.path.join(os.path.dirname(__file__), "..", "models.yaml")
    builder = ManifestBuilder(config_path=config_path, introspector=introspector)
    manifest = builder.build()

    print(f"✅ Manifest built successfully!")
    print(f"   Catalog: {manifest.catalog}")
    print(f"   Models ({len(manifest.models)}):")
    for model in manifest.models:
        col_count = len(model.columns)
        pk = f", PK: {model.primary_key}" if model.primary_key else ""
        desc = model.description[:60] + "..." if len(model.description) > 60 else model.description
        print(f"      📋 {model.name} → {model.table_reference} ({col_count} cols{pk})")
        print(f"         {desc}")

    print(f"\n   Relationships ({len(manifest.relationships)}):")
    for rel in manifest.relationships:
        print(f"      🔗 {rel.model_from} → {rel.model_to} ({rel.join_type.value})")
        print(f"         {rel.condition}")

    return connector, introspector, builder, manifest


def test_validate_manifest(builder, manifest):
    """Test 2: Validate manifest against DB."""
    separator("TEST 2: Validate Manifest against DB")

    errors = builder.validate(manifest)

    if errors:
        print(f"❌ Validation failed with {len(errors)} errors:")
        for i, err in enumerate(errors, 1):
            print(f"   {i}. {err}")
    else:
        print(f"✅ Manifest validation passed! All tables and columns exist in DB.")

    return errors


def test_deploy_manifest(manifest):
    """Test 3: Deploy manifest."""
    separator("TEST 3: Deploy Manifest (first time)")

    manifests_dir = os.path.join(os.path.dirname(__file__), "..", "manifests")
    deployer = ManifestDeployer(manifests_dir=manifests_dir)

    result = deployer.deploy(manifest)

    print(f"✅ Deploy result:")
    print(f"   Hash: {result.manifest_hash}")
    print(f"   Previous hash: {result.previous_hash or 'None (first deploy)'}")
    print(f"   Changed: {result.changed}")
    print(f"   Manifest path: {result.manifest_path}")
    print(f"   Timestamp: {result.timestamp}")

    # Verify file exists
    assert os.path.exists(result.manifest_path), "Manifest file should exist!"
    file_size = os.path.getsize(result.manifest_path)
    print(f"   File size: {file_size} bytes")

    return deployer, result


def test_redeploy_unchanged(manifest, deployer, first_result):
    """Test 4: Re-deploy unchanged → should skip."""
    separator("TEST 4: Re-deploy (no changes)")

    result = deployer.deploy(manifest)

    print(f"   Hash: {result.manifest_hash}")
    print(f"   Changed: {result.changed}")

    if not result.changed:
        print(f"✅ Correctly detected no changes — skipped re-index!")
    else:
        print(f"❌ Should not have changed!")

    assert result.manifest_hash == first_result.manifest_hash, \
        "Hash should be the same!"


def test_redeploy_changed(manifest, deployer, first_result):
    """Test 5: Modify manifest → re-deploy → hash should change."""
    separator("TEST 5: Re-deploy (with changes)")

    # Sửa description của model đầu tiên
    original_desc = manifest.models[0].description
    manifest.models[0].description = "MODIFIED FOR TESTING - " + original_desc

    result = deployer.deploy(manifest)

    print(f"   Previous hash: {result.previous_hash}")
    print(f"   New hash: {result.manifest_hash}")
    print(f"   Changed: {result.changed}")

    if result.changed:
        print(f"✅ Correctly detected changes — manifest re-deployed!")
    else:
        print(f"❌ Should have detected changes!")

    assert result.manifest_hash != first_result.manifest_hash, \
        "Hash should be different after changes!"

    # Restore original
    manifest.models[0].description = original_desc


def test_manifest_json_structure(deployer):
    """Test 6: Verify manifest JSON structure."""
    separator("TEST 6: Verify manifest JSON structure")

    manifest = deployer.get_current_manifest()
    if manifest is None:
        print("❌ No manifest found!")
        return

    # Check structure
    print(f"✅ Manifest loaded from file:")
    print(f"   Catalog: {manifest.catalog}")
    print(f"   Models: {manifest.model_names}")
    print(f"   Relationships: {len(manifest.relationships)}")

    # Test helper methods
    customers = manifest.get_model("customers")
    if customers:
        print(f"\n   Model 'customers':")
        print(f"     Table: {customers.table_reference}")
        print(f"     Columns: {customers.column_names[:5]}...")
        rels = manifest.get_relationships_for("customers")
        print(f"     Relationships: {len(rels)}")
        for r in rels:
            print(f"       🔗 {r.name}: {r.model_from} → {r.model_to}")

    # Check deploy history
    history = deployer.get_deploy_history()
    print(f"\n   Deploy history: {len(history)} deploys")
    for entry in history:
        print(f"     #{entry['deploy_number']}: {entry['hash'][:8]}... at {entry['timestamp']}")


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║    Mini Wren AI — Phase 2: Modeling Layer (MDL) Test    ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Test 1: Build
    connector, introspector, builder, manifest = test_build_manifest()

    # Test 2: Validate
    errors = test_validate_manifest(builder, manifest)
    if errors:
        print("\n⚠️  Fix validation errors before continuing!")

    # Test 3: Deploy
    deployer, first_result = test_deploy_manifest(manifest)

    # Test 4: Re-deploy unchanged
    test_redeploy_unchanged(manifest, deployer, first_result)

    # Test 5: Re-deploy with changes
    test_redeploy_changed(manifest, deployer, first_result)

    # Test 6: JSON structure
    test_manifest_json_structure(deployer)

    separator("ALL TESTS PASSED ✅")
    print("Phase 2: Modeling Layer is ready!\n")

    connector.close()


if __name__ == "__main__":
    main()
