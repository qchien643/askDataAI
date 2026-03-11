"""
Deploy Pipeline - Build manifest + index vào ChromaDB.

Tương đương POST /v1/semantics-preparations trong WrenAI gốc,
nhưng synchronous (trả kết quả luôn, không poll).

Luồng:
  read models.yaml → build manifest → deploy (save + hash) → index (ChromaDB)
"""

import logging
import os
from dataclasses import dataclass

from src.config import settings
from src.connectors.connection import SQLServerConnector
from src.connectors.schema_introspector import SchemaIntrospector
from src.modeling.manifest_builder import ManifestBuilder
from src.modeling.deploy import ManifestDeployer
from src.indexing.embedder import HuggingFaceEmbedder
from src.indexing.vector_store import VectorStore
from src.indexing.schema_indexer import SchemaIndexer

logger = logging.getLogger(__name__)


@dataclass
class DeployResult:
    success: bool
    message: str
    models_count: int = 0
    relationships_count: int = 0
    manifest_hash: str = ""
    indexed: bool = False
    db_schema_docs: int = 0
    table_desc_docs: int = 0


class DeployPipeline:
    """Build manifest từ models.yaml + index vào ChromaDB."""

    def __init__(
        self,
        models_yaml_path: str = "models.yaml",
        manifests_dir: str = "manifests",
        chroma_dir: str = "chroma_data",
    ):
        self._models_yaml_path = models_yaml_path
        self._manifests_dir = manifests_dir
        self._chroma_dir = chroma_dir

        self._connector = None
        self._manifest = None
        self._indexer = None

    def run(self) -> DeployResult:
        """
        Chạy full deploy pipeline.

        Returns:
            DeployResult.
        """
        try:
            # 1. Connect DB
            logger.info("Connecting to DB...")
            self._connector = SQLServerConnector(settings.connection_string)
            introspector = SchemaIntrospector(self._connector.engine)

            # 2. Build manifest
            logger.info(f"Building manifest from {self._models_yaml_path}...")
            builder = ManifestBuilder(
                config_path=self._models_yaml_path,
                introspector=introspector,
            )
            self._manifest = builder.build()

            # 3. Deploy (save + hash)
            logger.info("Deploying manifest...")
            deployer = ManifestDeployer(manifests_dir=self._manifests_dir)
            deploy_result = deployer.deploy(self._manifest)

            # 4. Index
            logger.info("Indexing into ChromaDB...")
            store = VectorStore(persist_dir=self._chroma_dir)
            embedder = HuggingFaceEmbedder(api_key=settings.huggingface_api_key)
            self._indexer = SchemaIndexer(vector_store=store, embedder=embedder)
            index_result = self._indexer.index(
                manifest=self._manifest,
                manifest_hash=deploy_result.manifest_hash,
            )

            return DeployResult(
                success=True,
                message="Deploy successful",
                models_count=len(self._manifest.models),
                relationships_count=len(self._manifest.relationships),
                manifest_hash=deploy_result.manifest_hash,
                indexed=index_result["indexed"],
                db_schema_docs=index_result.get("db_schema_docs", 0),
                table_desc_docs=index_result.get("table_desc_docs", 0),
            )

        except Exception as e:
            logger.error(f"Deploy failed: {e}")
            return DeployResult(
                success=False,
                message=f"Deploy failed: {str(e)}",
            )

    @property
    def manifest(self):
        return self._manifest

    @property
    def connector(self):
        return self._connector

    @property
    def indexer(self):
        return self._indexer
