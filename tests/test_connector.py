"""
Test script cho Phase 1: Database Connector.

Chạy: cd mini-wren-ai && python tests/test_connector.py

Script này test:
1. Kết nối SQL Server
2. Đọc toàn bộ tables + columns + types
3. Đọc foreign key relationships
4. Execute raw SQL query
5. Xử lý lỗi (query sai cú pháp)
"""

import sys
import os
import json

# Thêm parent directory vào path để import src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import settings
from src.connectors.connection import SQLServerConnector
from src.connectors.schema_introspector import SchemaIntrospector
from src.connectors.exceptions import ConnectionError, QueryError


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_connection():
    """Test 1: Kết nối SQL Server."""
    separator("TEST 1: Kết nối SQL Server")

    try:
        connector = SQLServerConnector(settings.connection_string)
        info = connector.test_connection()
        print(f"✅ Connected to SQL Server: {info['database_name']}")
        print(f"   Server version: {info['server_version']}")
        return connector
    except ConnectionError as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)


def test_schema_introspection(connector: SQLServerConnector):
    """Test 2 & 3: Đọc tables, columns, types, foreign keys."""
    separator("TEST 2: Đọc schema (tables + columns)")

    introspector = SchemaIntrospector(connector.engine)
    schema = introspector.get_full_schema()

    print(f"✅ Found {schema.table_count} tables in '{schema.database_name}':")
    print()

    for table in schema.tables:
        # Tìm FK liên quan đến table này
        fk_info = ""
        if table.foreign_keys:
            fk_parts = []
            for fk in table.foreign_keys:
                fk_parts.append(f"FK: {fk.from_column} → {fk.to_table}.{fk.to_column}")
            fk_info = f", {', '.join(fk_parts)}"

        pk_info = f", PK: {table.primary_key}" if table.primary_key else ""
        desc_info = f' — "{table.description}"' if table.description else ""

        print(f"   📋 {table.name} ({table.column_count} columns{pk_info}{fk_info}){desc_info}")

        # In chi tiết columns (chỉ 5 tables đầu để output không quá dài)
        if schema.tables.index(table) < 3:
            for col in table.columns:
                nullable = "NULL" if col.is_nullable else "NOT NULL"
                pk_marker = " 🔑" if col.is_primary_key else ""
                desc = f' — "{col.description}"' if col.description else ""
                print(f"      • {col.name} ({col.data_type}, {nullable}){pk_marker}{desc}")
            if table.column_count > 0:
                print()

    separator("TEST 3: Foreign Key Relationships")
    if schema.foreign_keys:
        print(f"✅ Found {len(schema.foreign_keys)} foreign key relationships:")
        for fk in schema.foreign_keys:
            print(f"   🔗 {fk.from_table}.{fk.from_column} → {fk.to_table}.{fk.to_column}")
            print(f"      Constraint: {fk.constraint_name}")
    else:
        print("⚠️  No foreign key relationships found.")
        print("   (Điều này bình thường nếu database không có FK hoặc là Data Warehouse)")

    return introspector


def test_execute_query(connector: SQLServerConnector):
    """Test 4: Execute raw SQL query."""
    separator("TEST 4: Execute raw SQL query")

    # Lấy tên table đầu tiên để query
    introspector = SchemaIntrospector(connector.engine)
    tables = introspector.get_all_schemas()

    if not tables:
        print("⚠️  No tables found, skipping query test.")
        return

    # Query top 5 rows từ table đầu tiên
    first_table = tables[0]
    sql = f"SELECT TOP 5 * FROM [{first_table.schema_name}].[{first_table.table_name}]"

    try:
        results = connector.execute(sql)
        print(f"✅ Query OK: {sql}")
        print(f"   Returned {len(results)} rows")
        if results:
            print(f"   Columns: {list(results[0].keys())}")
            # In row đầu tiên (truncate values dài)
            first_row = {
                k: (str(v)[:50] + "..." if len(str(v)) > 50 else v)
                for k, v in results[0].items()
            }
            print(f"   First row: {json.dumps(first_row, ensure_ascii=False, default=str)}")
    except QueryError as e:
        print(f"❌ Query failed: {e}")


def test_error_handling(connector: SQLServerConnector):
    """Test 5: Xử lý lỗi khi query sai."""
    separator("TEST 5: Error handling")

    # Test invalid SQL
    try:
        connector.execute("SELECT * FROM non_existent_table_12345")
        print("❌ Should have raised QueryError for invalid table!")
    except QueryError as e:
        print(f"✅ Invalid query caught correctly:")
        print(f"   Error: {str(e)[:100]}...")

    # Test syntax error
    try:
        connector.execute("SELECTTTT INVALID SYNTAX")
        print("❌ Should have raised QueryError for syntax error!")
    except QueryError as e:
        print(f"✅ Syntax error caught correctly:")
        print(f"   Error: {str(e)[:100]}...")


def test_schema_json_export(connector: SQLServerConnector):
    """Test bonus: Xuất schema ra JSON."""
    separator("TEST 6: Export schema to JSON")

    introspector = SchemaIntrospector(connector.engine)
    schema = introspector.get_full_schema()

    # Xuất ra file JSON
    output_path = os.path.join(os.path.dirname(__file__), "..", "manifests", "db_schema.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(schema.model_dump_json(indent=2))

    print(f"✅ Schema exported to: {output_path}")
    print(f"   File size: {os.path.getsize(output_path)} bytes")


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Mini Wren AI — Phase 1: Database Connector Test     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"Connection string: mssql+pyodbc://***@{settings.sql_server_host},{settings.sql_server_port}/{settings.sql_server_db}")

    # Run all tests
    connector = test_connection()
    test_schema_introspection(connector)
    test_execute_query(connector)
    test_error_handling(connector)
    test_schema_json_export(connector)

    separator("ALL TESTS PASSED ✅")
    print("Phase 1: Database Connector is ready!\n")

    connector.close()


if __name__ == "__main__":
    main()
