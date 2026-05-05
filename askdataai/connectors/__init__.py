"""
Connectors module — kết nối SQL Server và đọc schema.
"""

from askdataai.connectors.connection import SQLServerConnector
from askdataai.connectors.schema_introspector import (
    SchemaIntrospector,
    TableInfo,
    ColumnInfo,
    ForeignKeyInfo,
    DatabaseSchema,
)
from askdataai.connectors.exceptions import (
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
