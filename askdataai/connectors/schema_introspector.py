"""
SchemaIntrospector - Đọc schema (tables, columns, types, FK) từ SQL Server.

Tương đương MSSQLMetadata trong WrenAI gốc
(wren-engine/ibis-server/app/model/metadata/mssql.py),
nhưng dùng INFORMATION_SCHEMA queries trực tiếp qua SQLAlchemy.

Output dạng Pydantic models để dễ serialize JSON.
"""

import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from askdataai.connectors.exceptions import SchemaError

logger = logging.getLogger(__name__)


# ─── Pydantic Models cho Schema Output ───────────────────────────────────────

class ColumnInfo(BaseModel):
    """Thông tin 1 column trong table."""
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    description: str | None = None  # Từ extended properties (MS_Description)


class ForeignKeyInfo(BaseModel):
    """Thông tin 1 foreign key relationship."""
    constraint_name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class TableInfo(BaseModel):
    """Thông tin 1 table, bao gồm columns và FKs."""
    name: str  # schema.table_name
    schema_name: str
    table_name: str  # Tên table thật (không có schema prefix)
    description: str | None = None
    columns: list[ColumnInfo] = []
    primary_key: str | None = None
    foreign_keys: list[ForeignKeyInfo] = []

    @property
    def column_count(self) -> int:
        return len(self.columns)


class DatabaseSchema(BaseModel):
    """Toàn bộ schema của database."""
    database_name: str
    tables: list[TableInfo] = []
    foreign_keys: list[ForeignKeyInfo] = []

    @property
    def table_count(self) -> int:
        return len(self.tables)


# ─── SchemaIntrospector Class ─────────────────────────────────────────────────

class SchemaIntrospector:
    """
    Đọc metadata từ SQL Server database.
    
    Dùng INFORMATION_SCHEMA + sys views, giống approach của MSSQLMetadata
    trong WrenAI gốc nhưng thu gọn.

    Usage:
        introspector = SchemaIntrospector(connector.engine)
        schema = introspector.get_full_schema()
        print(schema.model_dump_json(indent=2))
    """

    # Schema hệ thống cần loại trừ
    EXCLUDED_SCHEMAS = ("sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                         "db_accessadmin", "db_securityadmin", "db_ddladmin",
                         "db_backupoperator", "db_datareader", "db_datawriter",
                         "db_denydatareader", "db_denydatawriter")

    def __init__(self, engine: Engine):
        self._engine = engine

    def get_tables(self) -> list[str]:
        """
        Lấy danh sách tên tables (schema.table_name), loại trừ system schemas.
        
        Returns:
            List tên tables dạng ["dbo.customers", "dbo.orders", ...]
        """
        sql = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA NOT IN :excluded
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text(sql),
                    {"excluded": self.EXCLUDED_SCHEMAS}
                )
                return [f"{row[0]}.{row[1]}" for row in result.fetchall()]
        except Exception as e:
            raise SchemaError(f"Failed to list tables: {e}") from e

    def get_table_schema(self, schema_name: str, table_name: str) -> TableInfo:
        """
        Lấy chi tiết columns + PK cho 1 table cụ thể.
        
        Args:
            schema_name: Schema name (vd: "dbo")
            table_name: Table name (vd: "customers")
            
        Returns:
            TableInfo object với columns và primary key.
        """
        # Query columns + PK + extended properties (descriptions)
        # Giống logic của MSSQLMetadata.get_table_list() nhưng cho 1 table
        sql = """
            SELECT 
                col.COLUMN_NAME,
                col.DATA_TYPE,
                col.IS_NULLABLE,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'YES' ELSE 'NO' END AS is_pk,
                CAST(tprop.value AS NVARCHAR(MAX)) AS table_comment,
                CAST(cprop.value AS NVARCHAR(MAX)) AS column_comment
            FROM INFORMATION_SCHEMA.COLUMNS col
            LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tab
                ON col.TABLE_SCHEMA = tab.TABLE_SCHEMA
                AND col.TABLE_NAME = tab.TABLE_NAME
                AND tab.CONSTRAINT_TYPE = 'PRIMARY KEY'
            LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk
                ON col.TABLE_SCHEMA = pk.TABLE_SCHEMA
                AND col.TABLE_NAME = pk.TABLE_NAME
                AND col.COLUMN_NAME = pk.COLUMN_NAME
                AND pk.CONSTRAINT_NAME = tab.CONSTRAINT_NAME
            LEFT JOIN sys.tables st
                ON st.name = col.TABLE_NAME 
                AND SCHEMA_NAME(st.schema_id) = col.TABLE_SCHEMA
            LEFT JOIN sys.extended_properties tprop
                ON tprop.major_id = st.object_id 
                AND tprop.minor_id = 0 
                AND tprop.name = 'MS_Description'
            LEFT JOIN sys.columns sc
                ON sc.object_id = st.object_id 
                AND sc.name = col.COLUMN_NAME
            LEFT JOIN sys.extended_properties cprop
                ON cprop.major_id = sc.object_id 
                AND cprop.minor_id = sc.column_id 
                AND cprop.name = 'MS_Description'
            WHERE col.TABLE_SCHEMA = :schema_name
              AND col.TABLE_NAME = :table_name
            ORDER BY col.ORDINAL_POSITION
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text(sql),
                    {"schema_name": schema_name, "table_name": table_name}
                )
                rows = result.fetchall()

                if not rows:
                    raise SchemaError(
                        f"Table '{schema_name}.{table_name}' not found or has no columns."
                    )

                columns = []
                primary_key = None
                table_description = None

                for row in rows:
                    col_name, data_type, is_nullable, is_pk, table_comment, col_comment = row

                    if table_comment and not table_description:
                        table_description = table_comment

                    is_pk_bool = is_pk == "YES"
                    if is_pk_bool:
                        primary_key = col_name

                    columns.append(ColumnInfo(
                        name=col_name,
                        data_type=data_type,
                        is_nullable=(is_nullable.upper() == "YES"),
                        is_primary_key=is_pk_bool,
                        description=col_comment,
                    ))

                return TableInfo(
                    name=f"{schema_name}.{table_name}",
                    schema_name=schema_name,
                    table_name=table_name,
                    description=table_description,
                    columns=columns,
                    primary_key=primary_key,
                )
        except SchemaError:
            raise
        except Exception as e:
            raise SchemaError(
                f"Failed to get schema for '{schema_name}.{table_name}': {e}"
            ) from e

    def get_foreign_keys(self) -> list[ForeignKeyInfo]:
        """
        Lấy tất cả foreign key relationships trong database.
        
        Query giống MSSQLMetadata.get_constraints() trong WrenAI gốc.
        
        Returns:
            List ForeignKeyInfo objects.
        """
        sql = """
            SELECT 
                fk.name AS constraint_name,
                sch.name AS table_schema,
                t.name AS table_name,
                c.name AS column_name,
                ref_sch.name AS referenced_table_schema,
                ref_t.name AS referenced_table_name,
                ref_c.name AS referenced_column_name
            FROM sys.foreign_keys AS fk
            JOIN sys.foreign_key_columns AS fkc 
                ON fk.object_id = fkc.constraint_object_id
            JOIN sys.tables AS t 
                ON fkc.parent_object_id = t.object_id
            JOIN sys.schemas AS sch 
                ON t.schema_id = sch.schema_id
            JOIN sys.columns AS c 
                ON fkc.parent_column_id = c.column_id 
                AND c.object_id = t.object_id
            JOIN sys.tables AS ref_t 
                ON fkc.referenced_object_id = ref_t.object_id
            JOIN sys.schemas AS ref_sch 
                ON ref_t.schema_id = ref_sch.schema_id
            JOIN sys.columns AS ref_c 
                ON fkc.referenced_column_id = ref_c.column_id 
                AND ref_c.object_id = ref_t.object_id
            ORDER BY fk.name
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(sql))
                rows = result.fetchall()

                return [
                    ForeignKeyInfo(
                        constraint_name=row[0],
                        from_table=f"{row[1]}.{row[2]}",
                        from_column=row[3],
                        to_table=f"{row[4]}.{row[5]}",
                        to_column=row[6],
                    )
                    for row in rows
                ]
        except Exception as e:
            raise SchemaError(f"Failed to get foreign keys: {e}") from e

    def get_all_schemas(self) -> list[TableInfo]:
        """
        Lấy schema tất cả tables (columns + PK), không bao gồm FK.
        
        Returns:
            List TableInfo objects.
        """
        # Query tất cả tables + columns 1 lần, giống MSSQLMetadata.get_table_list()
        sql = """
            SELECT 
                col.TABLE_SCHEMA,
                col.TABLE_NAME,
                col.COLUMN_NAME,
                col.DATA_TYPE,
                col.IS_NULLABLE,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'YES' ELSE 'NO' END AS is_pk,
                CAST(tprop.value AS NVARCHAR(MAX)) AS table_comment,
                CAST(cprop.value AS NVARCHAR(MAX)) AS column_comment
            FROM INFORMATION_SCHEMA.COLUMNS col
            LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tab
                ON col.TABLE_SCHEMA = tab.TABLE_SCHEMA
                AND col.TABLE_NAME = tab.TABLE_NAME
                AND tab.CONSTRAINT_TYPE = 'PRIMARY KEY'
            LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk
                ON col.TABLE_SCHEMA = pk.TABLE_SCHEMA
                AND col.TABLE_NAME = pk.TABLE_NAME
                AND col.COLUMN_NAME = pk.COLUMN_NAME
                AND pk.CONSTRAINT_NAME = tab.CONSTRAINT_NAME
            LEFT JOIN sys.tables st
                ON st.name = col.TABLE_NAME 
                AND SCHEMA_NAME(st.schema_id) = col.TABLE_SCHEMA
            LEFT JOIN sys.extended_properties tprop
                ON tprop.major_id = st.object_id 
                AND tprop.minor_id = 0 
                AND tprop.name = 'MS_Description'
            LEFT JOIN sys.columns sc
                ON sc.object_id = st.object_id 
                AND sc.name = col.COLUMN_NAME
            LEFT JOIN sys.extended_properties cprop
                ON cprop.major_id = sc.object_id 
                AND cprop.minor_id = sc.column_id 
                AND cprop.name = 'MS_Description'
            WHERE col.TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
            ORDER BY col.TABLE_SCHEMA, col.TABLE_NAME, col.ORDINAL_POSITION
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(sql))
                rows = result.fetchall()

                # Group rows thành tables (giống logic MSSQLMetadata)
                tables_dict: dict[str, TableInfo] = {}

                for row in rows:
                    (schema_, tbl_name, col_name, data_type,
                     is_nullable, is_pk, table_comment, col_comment) = row

                    full_name = f"{schema_}.{tbl_name}"

                    if full_name not in tables_dict:
                        tables_dict[full_name] = TableInfo(
                            name=full_name,
                            schema_name=schema_,
                            table_name=tbl_name,
                            description=table_comment,
                            columns=[],
                            primary_key=None,
                        )

                    is_pk_bool = is_pk == "YES"
                    if is_pk_bool:
                        tables_dict[full_name].primary_key = col_name

                    tables_dict[full_name].columns.append(ColumnInfo(
                        name=col_name,
                        data_type=data_type,
                        is_nullable=(is_nullable.upper() == "YES"),
                        is_primary_key=is_pk_bool,
                        description=col_comment,
                    ))

                return list(tables_dict.values())
        except Exception as e:
            raise SchemaError(f"Failed to get all schemas: {e}") from e

    def get_full_schema(self) -> DatabaseSchema:
        """
        Lấy toàn bộ schema: tables + columns + PKs + FKs → 1 object.
        Đây là method chính, gom tất cả lại.

        Returns:
            DatabaseSchema object, có thể serialize bằng .model_dump_json()
        """
        try:
            # Lấy database name
            with self._engine.connect() as conn:
                db_name = conn.execute(text("SELECT DB_NAME()")).scalar()

            # Lấy tables + columns
            tables = self.get_all_schemas()

            # Lấy foreign keys
            foreign_keys = self.get_foreign_keys()

            # Gắn FK vào đúng table
            fk_by_table: dict[str, list[ForeignKeyInfo]] = {}
            for fk in foreign_keys:
                fk_by_table.setdefault(fk.from_table, []).append(fk)

            for table in tables:
                table.foreign_keys = fk_by_table.get(table.name, [])

            logger.info(
                f"Schema loaded: {db_name} — "
                f"{len(tables)} tables, {len(foreign_keys)} foreign keys"
            )

            return DatabaseSchema(
                database_name=db_name,
                tables=tables,
                foreign_keys=foreign_keys,
            )
        except SchemaError:
            raise
        except Exception as e:
            raise SchemaError(f"Failed to get full schema: {e}") from e
