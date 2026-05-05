"""
Custom exceptions cho connectors module.
Tương đương UnprocessableEntityError, QueryDryRunError trong WrenAI gốc.
"""


class ConnectorError(Exception):
    """Base exception for connector errors."""
    pass


class ConnectionError(ConnectorError):
    """Lỗi kết nối SQL Server (sai host, sai credentials, timeout...)"""
    pass


class QueryError(ConnectorError):
    """Lỗi khi thực thi query (sai cú pháp, timeout, permission...)"""
    pass


class SchemaError(ConnectorError):
    """Lỗi khi đọc schema (table không tồn tại, permission...)"""
    pass
