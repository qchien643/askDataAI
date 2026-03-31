"""
Config module - đọc settings từ .env file.
Tương đương phần config trong wren-ai-service/config.yaml nhưng đơn giản hơn.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

# Load .env file từ thư mục gốc project
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    # SQL Server
    sql_server_host: str = Field(default="localhost", alias="SQL_SERVER_HOST")
    sql_server_port: int = Field(default=1433, alias="SQL_SERVER_PORT")
    sql_server_db: str = Field(default="AdventureWorksDW2025", alias="SQL_SERVER_DB")
    sql_server_user: str = Field(default="sa", alias="SQL_SERVER_USER")
    sql_server_pass: str = Field(default="", alias="SQL_SERVER_PASS")

    # LLM (OpenAI-compatible)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )

    # HuggingFace (Embeddings)
    huggingface_api_key: str = Field(default="", alias="HUGGINGFACE_API_KEY")

    # ChromaDB
    chroma_persist_dir: str = Field(default="./chroma_data", alias="CHROMA_PERSIST_DIR")

    # Advanced Pipeline Settings
    num_candidates: int = Field(default=3, alias="NUM_CANDIDATES")
    enable_column_pruning: bool = Field(default=True, alias="ENABLE_COLUMN_PRUNING")
    enable_cot_reasoning: bool = Field(default=True, alias="ENABLE_COT_REASONING")
    enable_schema_linking: bool = Field(default=True, alias="ENABLE_SCHEMA_LINKING")
    enable_voting: bool = Field(default=True, alias="ENABLE_VOTING")
    glossary_path: str = Field(default="./glossary.yaml", alias="GLOSSARY_PATH")
    memory_path: str = Field(default="./semantic_memory.json", alias="MEMORY_PATH")

    @property
    def connection_string(self) -> str:
        """SQLAlchemy connection string cho SQL Server qua pyodbc."""
        from urllib.parse import quote_plus

        password = quote_plus(self.sql_server_pass)
        # Inside Docker, localhost refers to the container itself.
        # Auto-resolve to host.docker.internal to reach the host machine.
        host = self.sql_server_host
        if Path("/.dockerenv").exists() and host in ("localhost", "127.0.0.1"):
            host = "host.docker.internal"
        return (
            f"mssql+pyodbc://{self.sql_server_user}:{password}"
            f"@{host},{self.sql_server_port}"
            f"/{self.sql_server_db}"
            f"?driver=ODBC+Driver+17+for+SQL+Server"
            f"&TrustServerCertificate=yes"
        )

    class Config:
        env_file = ".env"
        populate_by_name = True


# Singleton instance
settings = Settings()
