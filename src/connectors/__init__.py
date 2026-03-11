"""
Connectors module — kết nối SQL Server và đọc schema.
"""

from src.connectors.connection import SQLServerConnector
from src.connectors.schema_introspector import (
    SchemaIntrospector,
    TableInfo,
    ColumnInfo,
    ForeignKeyInfo,
    DatabaseSchema,
)
from src.connectors.exceptions import (
    ConnectorError,
    ConnectionError,
    QueryError,
    SchemaError,
)

__all__ = [
    "SQLServerConnector",
    "SchemaIntrospector",
    "TableInfo",
    "ColumnInfo",
    "ForeignKeyInfo",
    "DatabaseSchema",
    "ConnectorError",
    "ConnectionError",
    "QueryError",
    "SchemaError",
]
