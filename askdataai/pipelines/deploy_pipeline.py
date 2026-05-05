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

from askdataai.config import settings
from askdataai.connectors.connection import SQLServerConnector
from askdataai.connectors.schema_introspector import SchemaIntrospector
from askdataai.modeling.manifest_builder import ManifestBuilder
from askdataai.modeling.deploy import ManifestDeployer
from askdataai.indexing.embedder import OpenAIEmbedder
from askdataai.indexing.vector_store import VectorStore
from askdataai.indexing.schema_indexer import SchemaIndexer

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
        models_yaml_path: str = "configs/models.yaml",
        manifests_dir: str = "data/manifests",
        chroma_dir: str = "data/chroma_data",
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
            embedder = OpenAIEmbedder(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
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
