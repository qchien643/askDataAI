"""
MDL Schema - Pydantic models cho Modeling Definition Language.

Bản rút gọn của wren-engine/mcp-server/mdl.schema.json.
Định nghĩa cấu trúc semantic layer: Column, Relationship, Model, Manifest.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JoinType(str, Enum):
    """Loại join giữa 2 models."""
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"


class Column(BaseModel):
    """
    1 column trong model.
    
    - name: tên cột gốc trong DB (vd: CustomerAlternateKey)
    - display_name: tên hiển thị cho AI đọc (vd: "Mã khách hàng thay thế")
    - type: data type
    - description: mô tả ý nghĩa (rất quan trọng cho AI!)
    - is_calculated: true nếu là calculated field
    - expression: SQL expression nếu là calculated field
    """
    name: str                          # Tên cột gốc trong DB
    display_name: str = ""             # Tên cho AI đọc (LLM-friendly)
    type: str
    description: str = ""
    is_calculated: bool = False
    expression: str | None = None

    @property
    def actual_source(self) -> str:
        """Tên cột thật trong DB (luôn là name)."""
        return self.name

    @property
    def ai_name(self) -> str:
        """Tên mà AI sẽ dùng: ưu tiên display_name, fallback name."""
        return self.display_name or self.name


class Relationship(BaseModel):
    """
    Quan hệ giữa 2 models.
    
    - name: tên relationship (unique)
    - model_from: tên model chứa FK
    - model_to: tên model được reference
    - join_type: ONE_TO_ONE, ONE_TO_MANY, MANY_TO_ONE, MANY_TO_MANY
    - condition: điều kiện join, vd: "orders.customer_id = customers.id"
    """
    name: str
    model_from: str
    model_to: str
    join_type: JoinType
    condition: str


class Model(BaseModel):
    """
    1 Model = 1 table trong DB + metadata cho AI.
    
    - name: tên model (AI dùng tên này)
    - table_reference: schema.table_name thật trong DB
    - description: mô tả model chứa data gì
    - columns: danh sách columns
    - primary_key: tên column là PK
    """
    name: str
    table_reference: str  # vd: "dbo.DimCustomer"
    description: str = ""
    columns: list[Column] = []
    primary_key: str | None = None

    @property
    def column_names(self) -> list[str]:
        return [col.name for col in self.columns]


class Manifest(BaseModel):
    """
    Toàn bộ Semantic Layer - tương đương MDL trong Wren AI gốc.
    
    - catalog: tên database
    - schema_name: schema mặc định (vd: "dbo")
    - models: danh sách models
    - relationships: quan hệ giữa models
    """
    catalog: str  # database name
    schema_name: str = "dbo"
    models: list[Model] = []
    relationships: list[Relationship] = []

    @property
    def model_names(self) -> list[str]:
        return [m.name for m in self.models]

    def get_model(self, name: str) -> Model | None:
        """Tìm model theo tên."""
        for m in self.models:
            if m.name == name:
                return m
        return None

    def get_relationships_for(self, model_name: str) -> list[Relationship]:
        """Lấy tất cả relationships liên quan đến 1 model."""
        return [
            r for r in self.relationships
            if r.model_from == model_name or r.model_to == model_name
        ]
