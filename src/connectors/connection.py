"""
SQLServerConnector - Kết nối và thực thi query trên SQL Server.

Tương đương MSSqlConnector + SimpleConnector trong WrenAI gốc
(wren-engine/ibis-server/app/model/connector.py),
nhưng dùng sqlalchemy + pyodbc thay vì ibis.

Chức năng:
  - Kết nối SQL Server bằng connection string
  - Test connection (SELECT 1)
  - Execute query an toàn (read-only, có timeout)
"""

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    OperationalError,
    ProgrammingError,
    DBAPIError,
)

from src.connectors.exceptions import (
    ConnectionError,
    QueryError,
)

logger = logging.getLogger(__name__)


class SQLServerConnector:
    """
    Quản lý kết nối và thực thi query trên SQL Server.
    
    Usage:
        from src.config import settings
        connector = SQLServerConnector(settings.connection_string)
        connector.test_connection()
        results = connector.execute("SELECT TOP 10 * FROM customers")
    """

    def __init__(self, connection_string: str, query_timeout: int = 30):
        """
        Khởi tạo connector.

        Args:
            connection_string: SQLAlchemy connection string cho SQL Server.
            query_timeout: Timeout mặc định cho mỗi query (giây).
        """
        self._connection_string = connection_string
        self._query_timeout = query_timeout
        self._engine: Engine | None = None

        try:
            self._engine = create_engine(
                connection_string,
                connect_args={"timeout": query_timeout},
                pool_pre_ping=True,  # Tự reconnect nếu connection chết
                pool_size=5,
                max_overflow=10,
            )
            logger.info("SQLAlchemy engine created successfully.")
        except Exception as e:
            raise ConnectionError(f"Failed to create engine: {e}") from e

    @property
    def engine(self) -> Engine:
        """Expose engine cho SchemaIntrospector."""
        if self._engine is None:
            raise ConnectionError("Engine has not been initialized.")
        return self._engine

    def test_connection(self) -> dict[str, str]:
        """
        Test kết nối bằng SELECT 1 + lấy tên database.
        
        Returns:
            Dict chứa database_name và server_version.
        
        Raises:
            ConnectionError: Nếu không kết nối được.
        """
        try:
            with self._engine.connect() as conn:
                # Test basic connectivity
                conn.execute(text("SELECT 1"))

                # Lấy thông tin database
                db_name = conn.execute(text("SELECT DB_NAME()")).scalar()
                version = conn.execute(
                    text("SELECT SERVERPROPERTY('ProductVersion')")
                ).scalar()

                logger.info(f"Connected to SQL Server: {db_name} (v{version})")
                return {
                    "database_name": db_name,
                    "server_version": str(version),
                    "status": "connected",
                }
        except (OperationalError, DBAPIError) as e:
            raise ConnectionError(
                f"Cannot connect to SQL Server: {e}"
            ) from e

    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Thực thi query SELECT, trả kết quả dạng list[dict] (JSON-serializable).

        Args:
            sql: Câu SQL cần chạy (chỉ SELECT).
            params: Tham số bind parameters (optional).
            timeout: Override timeout cho query này (giây).

        Returns:
            List of dicts, mỗi dict là 1 row: {"col_name": value, ...}

        Raises:
            QueryError: Nếu query lỗi cú pháp, timeout, hoặc vấn đề khác.
        """
        effective_timeout = timeout or self._query_timeout

        try:
            with self._engine.connect() as conn:
                # Set query timeout cho connection này
                conn.execute(
                    text(f"SET LOCK_TIMEOUT {effective_timeout * 1000}")
                )

                result = conn.execute(text(sql), params or {})
                rows = result.fetchall()
                columns = list(result.keys())

                # Convert rows thành list[dict]
                return [
                    {col: self._serialize_value(row[i]) for i, col in enumerate(columns)}
                    for row in rows
                ]

        except ProgrammingError as e:
            raise QueryError(f"SQL syntax error: {e}") from e
        except OperationalError as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                raise QueryError(
                    f"Query timeout after {effective_timeout}s: {e}"
                ) from e
            raise QueryError(f"Query execution error: {e}") from e
        except DBAPIError as e:
            raise QueryError(f"Database error: {e}") from e
        except Exception as e:
            raise QueryError(f"Unexpected error executing query: {e}") from e

    def execute_raw(self, sql: str) -> Any:
        """
        Thực thi query và trả về scalar result (dùng cho internal queries).
        
        Returns:
            Scalar value hoặc None.
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(sql))
                return result.scalar()
        except Exception as e:
            raise QueryError(f"Error executing raw query: {e}") from e

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """Convert value thành JSON-serializable type."""
        import datetime
        import decimal

        if value is None:
            return None
        if isinstance(value, (int, float, str, bool)):
            return value
        if isinstance(value, decimal.Decimal):
            return float(value)
        if isinstance(value, (datetime.datetime, datetime.date)):
            return value.isoformat()
        if isinstance(value, datetime.time):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.hex()
        return str(value)

    def close(self):
        """Đóng engine và giải phóng connections."""
        if self._engine:
            self._engine.dispose()
            logger.info("SQLAlchemy engine disposed.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self):
        # Mask password trong repr
        return f"SQLServerConnector(host=***,db=***)"
