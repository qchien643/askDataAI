"""
Description Pipeline — 6-phase orchestrator for XiYan auto-description.

Orchestrates the full pipeline:
  Phase 0: Index existing descriptions into ChromaDB
  Phase 1: Extract style guide + domain understanding
  Phase 2: Batch SQL profiling for empty columns
  Phase 3: Batch column type classification
  Phase 4: Table-level agent generates descriptions
  Phase 5: Persist results into models.yaml

Provides both sync run() and async SSE run_stream() methods.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from askdataai.config import Settings
from askdataai.connectors.connection import SQLServerConnector
from askdataai.generation.auto_describe.agent import DescAgent
from askdataai.generation.auto_describe.indexer import DescriptionIndexer
from askdataai.generation.auto_describe.prompts import STYLE_GUIDE_PROMPT, DB_UNDERSTANDING_PROMPT
from askdataai.generation.llm_client import LLMClient
from askdataai.generation.auto_describe.schema_profiler import SchemaProfiler
from askdataai.generation.auto_describe.type_engine import TypeEngine
from askdataai.indexing.embedder import OpenAIEmbedder
from askdataai.indexing.vector_store import VectorStore
from askdataai.modeling.manifest_builder import ManifestBuilder

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the description pipeline."""

    mode: str = "merge"               # merge | overwrite
    n_examples: int = 3               # ChromaDB results per search
    max_tool_calls: int = 4           # Max agent tool calls per table
    model: str = "gpt-4.1-mini"       # LLM model
    temperature: float = 0.1
    batch_classify_size: int = 20
    sample_limit: int = 20
    tables: list[str] | None = None   # None = all tables with empty cols


@dataclass
class PipelineEvent:
    """SSE event for streaming progress."""

    phase: str
    status: str           # running | done | error
    progress: str
    table: str = ""
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        payload = {
            "phase": self.phase,
            "status": self.status,
            "progress": self.progress,
        }
        if self.table:
            payload["table"] = self.table
        if self.data:
            payload.update(self.data)
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class DescriptionPipeline:
    """
    6-phase orchestrator for automated schema description generation.

    Usage:
        pipeline = DescriptionPipeline(settings)
        # Sync
        results = await pipeline.run(config)
        # SSE streaming
        async for event in pipeline.run_stream(config):
            yield event.to_sse()
    """

    def __init__(self, settings: Settings):
        self._settings = settings

        # Reuse existing infrastructure
        self._llm = LLMClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self._connector = SQLServerConnector(settings.connection_string)
        self._embedder = OpenAIEmbedder(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self._vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
        self._models_yaml = Path("configs/models.yaml")
        self._manifest_builder = ManifestBuilder(self._models_yaml)

    async def run(self, config: PipelineConfig | None = None) -> dict[str, Any]:
        """
        Run the full 6-phase pipeline.

        Returns:
            Summary dict with updated_tables, total_descriptions, etc.
        """
        config = config or PipelineConfig()
        results: dict[str, Any] = {"updated_tables": [], "total_descriptions": 0}

        async for event in self.run_stream(config):
            if event.phase == "complete":
                results = event.data
                break

        return results

    async def run_stream(
        self, config: PipelineConfig | None = None
    ) -> AsyncIterator[PipelineEvent]:
        """
        Run the pipeline with SSE event streaming.

        Yields PipelineEvent for each phase transition and progress update.
        """
        config = config or PipelineConfig()
        manifest = self._manifest_builder.build()

        # ── Phase 0: Index existing descriptions ──────────────────
        yield PipelineEvent("indexing", "running", "Indexing existing descriptions...")

        indexer = DescriptionIndexer(self._vector_store, self._embedder)
        indexed_count = indexer.index_from_manifest(manifest)

        yield PipelineEvent(
            "indexing", "done",
            f"Indexed {indexed_count} existing descriptions"
        )

        # ── Phase 1: Extract context ─────────────────────────────
        yield PipelineEvent("context", "running", "Extracting style guide...")

        style_guide = await self._extract_style_guide(manifest)
        domain_info = await self._extract_domain_info(manifest)

        yield PipelineEvent(
            "context", "done",
            f"Style: {style_guide.get('language', '?')}, "
            f"Domain: {domain_info.get('domain', '?')}"
        )

        # ── Phase 2: SQL Profiling ───────────────────────────────
        yield PipelineEvent("profiling", "running", "Profiling empty columns...")

        profiler = SchemaProfiler(
            connector=self._connector,
            sample_limit=config.sample_limit,
        )

        # Determine target tables
        target_models = self._get_target_models(manifest, config)
        profile_cache = {}

        for model in target_models:
            empty_cols = [
                {"name": c.name, "type": c.type,
                 "enum_values": c.enum_values, "description": c.description}
                for c in model.columns
                if not c.description.strip()
            ]
            if empty_cols:
                table_profiles = profiler.profile_table(
                    table_ref=model.table_reference,
                    columns=empty_cols,
                    primary_key=model.primary_key,
                )
                profile_cache.update(table_profiles)

        yield PipelineEvent(
            "profiling", "done",
            f"Profiled {len(profile_cache)} columns"
        )

        # ── Phase 3: Batch Classification ────────────────────────
        yield PipelineEvent("classifying", "running", "Classifying column types...")

        type_engine = TypeEngine(self._llm, batch_size=config.batch_classify_size)
        all_classifications: dict[str, dict[str, dict]] = {}  # table -> col -> class

        for model in target_models:
            empty_cols = [
                {"name": c.name, "type": c.type}
                for c in model.columns
                if not c.description.strip()
            ]
            if empty_cols:
                rels = manifest.get_relationships_for(model.name)
                rel_dicts = [
                    {"name": r.name, "from": r.model_from,
                     "to": r.model_to, "condition": r.condition}
                    for r in rels
                ]
                classifications = type_engine.classify_batch(
                    columns=empty_cols,
                    table_name=model.name,
                    primary_key=model.primary_key,
                    relationships=rel_dicts,
                )
                all_classifications[model.name] = classifications

        yield PipelineEvent(
            "classifying", "done",
            f"Classified columns for {len(all_classifications)} tables"
        )

        # ── Phase 4: Agent Loop ──────────────────────────────────
        agent = DescAgent(
            api_key=self._settings.openai_api_key,
            base_url=self._settings.openai_base_url,
            model=config.model,
            temperature=config.temperature,
            max_tool_calls=config.max_tool_calls,
            indexer=indexer,
            profile_cache=profile_cache,
            manifest=manifest,
        )

        all_descriptions: dict[str, dict] = {}  # table -> {col -> desc_data}
        total_generated = 0

        for model in target_models:
            empty_cols = [
                {"name": c.name, "type": c.type}
                for c in model.columns
                if not c.description.strip()
            ]
            if not empty_cols:
                continue

            yield PipelineEvent(
                "agent", "running",
                f"Generating descriptions for {model.name} "
                f"({len(empty_cols)} columns)...",
                table=model.name,
            )

            existing_described = [
                {"name": c.name, "description": c.description, "type": c.type}
                for c in model.columns
                if c.description.strip()
            ]

            try:
                descriptions = await agent.generate_for_table(
                    table_name=model.name,
                    empty_columns=empty_cols,
                    classifications=all_classifications.get(model.name, {}),
                    style_guide=style_guide,
                    domain_info=domain_info,
                    table_description=model.description,
                    primary_key=model.primary_key,
                    existing_described=existing_described,
                )

                all_descriptions[model.name] = descriptions
                total_generated += len(descriptions)

                yield PipelineEvent(
                    "agent", "done",
                    f"Generated {len(descriptions)} descriptions for {model.name}",
                    table=model.name,
                    data={"descriptions": {
                        k: v.get("description", "") for k, v in descriptions.items()
                    }},
                )

            except Exception as e:
                logger.error(f"Agent failed for {model.name}: {e}")
                yield PipelineEvent(
                    "agent", "error",
                    f"Failed for {model.name}: {str(e)[:100]}",
                    table=model.name,
                )

        # ── Phase 5: Persist ─────────────────────────────────────
        yield PipelineEvent(
            "persist", "running",
            f"Saving {total_generated} descriptions to models.yaml..."
        )

        updated_tables = self._persist_descriptions(
            all_descriptions, config.mode
        )

        yield PipelineEvent("persist", "done", f"Updated {len(updated_tables)} tables")

        # ── Complete ─────────────────────────────────────────────
        yield PipelineEvent(
            "complete", "done",
            f"Pipeline complete: {total_generated} descriptions for "
            f"{len(updated_tables)} tables",
            data={
                "updated_tables": updated_tables,
                "total_descriptions": total_generated,
                "indexed": indexed_count,
                "profiled": len(profile_cache),
            },
        )

    # ─── Private Methods ──────────────────────────────────────────

    def _get_target_models(self, manifest, config: PipelineConfig) -> list:
        """Get list of models to process."""
        if config.tables:
            return [
                m for m in manifest.models
                if m.name in config.tables
            ]
        return manifest.models

    async def _extract_style_guide(self, manifest) -> dict:
        """Phase 1a: Extract style guide from existing descriptions."""
        descriptions = []
        for model in manifest.models:
            for col in model.columns:
                if col.description.strip():
                    descriptions.append(
                        f"[{model.name}.{col.name}] ({col.type}): {col.description}"
                    )

        if not descriptions:
            return {"language": "EN", "format_patterns": [], "typical_length": "medium"}

        prompt = STYLE_GUIDE_PROMPT.format(
            descriptions="\n".join(descriptions[:40])  # Limit for context
        )

        try:
            result = self._llm.chat_json(
                user_prompt=prompt,
                system_prompt="You are a technical writing analyst.",
            )
            return result
        except Exception as e:
            logger.error(f"Style guide extraction failed: {e}")
            return {"language": "EN", "format_patterns": [], "typical_length": "medium"}

    async def _extract_domain_info(self, manifest) -> dict:
        """Phase 1b: Extract domain understanding from schema."""
        tables_summary = "\n".join(
            f"Table {m.name} ({m.table_reference}): "
            f"{', '.join(c.name for c in m.columns[:8])}..."
            for m in manifest.models
        )

        prompt = DB_UNDERSTANDING_PROMPT.format(schema_ddl=tables_summary)

        try:
            result = self._llm.chat_json(
                user_prompt=prompt,
                system_prompt="You are a database architect.",
            )
            return result
        except Exception as e:
            logger.error(f"Domain extraction failed: {e}")
            return {"domain": "unknown"}

    def _persist_descriptions(
        self, all_descriptions: dict[str, dict], mode: str
    ) -> list[str]:
        """
        Phase 5: Persist generated descriptions to models.yaml.

        Reuses the ManifestBuilder's YAML read/write pattern.
        """
        import yaml

        yaml_path = self._models_yaml
        updated_tables: list[str] = []

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            models_list = data.get("models", [])

            for model_data in models_list:
                model_name = model_data.get("name", "")
                if model_name not in all_descriptions:
                    continue

                descriptions = all_descriptions[model_name]
                columns = model_data.get("columns", [])
                col_map = {c["name"]: c for c in columns}

                for col_name, desc_data in descriptions.items():
                    if col_name not in col_map:
                        continue

                    col = col_map[col_name]
                    existing_desc = col.get("description", "").strip()

                    # Merge mode: only update if empty
                    if mode == "merge" and existing_desc:
                        continue

                    desc_text = desc_data
                    enum_vals = []

                    # Handle dict result format
                    if isinstance(desc_data, dict):
                        desc_text = desc_data.get("description", "")
                        enum_vals = desc_data.get("enum_values", [])

                    col["description"] = desc_text
                    if enum_vals:
                        col["enum_values"] = enum_vals

                updated_tables.append(model_name)

            # Write back
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                          sort_keys=False, width=120)

            logger.info(f"Persisted descriptions for {len(updated_tables)} tables")

        except Exception as e:
            logger.error(f"Failed to persist descriptions: {e}")

        return updated_tables
