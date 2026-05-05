# askdataai/generation/ — LLM stages

Các stage sinh/biến đổi text qua LLM (OpenAI). Pipeline 14-stage tổ chức theo file riêng, được orchestrate bởi `pipelines/ask_pipeline.py`.

## File map (theo thứ tự pipeline)

| Stage | File | Class | LLM? |
|---|---|---|:---:|
| 0 | `../security/pi_guardrail.py` | `PIGuardrail` | × |
| 0.5 | `conversation_context.py` | `ConversationContextEngine` | × (mem0) |
| 1 | `pre_filter.py` | `PreFilter` | × |
| 2 | `instruction_matcher.py` | `InstructionMatcher` | × |
| 3 | `intent_classifier.py` | `IntentClassifier` | ✓ |
| 4 | `sub_intent.py` | `SubIntentDetector` | ✓ (fallback) |
| — | `schema_explorer.py` | `SchemaExplorer` | ✓ |
| 10 | `semantic_memory.py` | `SemanticMemory` | × (Jaccard) |
| 11 | `sql_reasoner.py` | `SQLReasoner` (CoT) | ✓ |
| 12 | `candidate_generator.py` | `CandidateGenerator` | ✓ ×N |
| 12 | `execution_voter.py` | `ExecutionVoter` | × |
| — | `sql_generator.py` | `SQLGenerator` (single-pass) | ✓ |
| 13 | `sql_corrector.py` | `SQLCorrector` | ✓ retry |
| — | `sql_rewriter.py` | `SQLRewriter` (model→DB names) | × |
| — | `chart_generator.py` | `ChartGenerator` (Vega-Lite) | ✓ |
| — | `llm_client.py` | `LLMClient` (OpenAI wrapper) | — |

## auto_describe/ sub-package

Feature LLM-driven schema description (auto-generate Vietnamese description cho table/column).

```
auto_describe/
├── pipeline.py           # 6-phase orchestrator (entry: AutoDescribePipeline.run())
├── agent.py              # LLM agent loop
├── indexer.py            # Description indexing into ChromaDB
├── prompts.py            # Vietnamese prompt templates
├── tools.py              # LLM tool definitions
├── schema_profiler.py    # Column distribution analysis
└── type_engine.py        # SQL type inference
```

Được gọi từ `server.py` qua endpoint `POST /v1/models/auto-describe`. Không thuộc 14-stage chính.

## Conventions

- **DI**: nhận `LLMClient` qua constructor. Không tạo client mới mỗi stage.
- **Output**: dataclass/Pydantic với field rõ ràng. Tránh dict ad-hoc.
- **Prompts**: tiếng Việt cho user-facing reasoning; English cho system instructions.
- **Temperature**: precise stages dùng 0.0; creative stages 0.3-0.7. Khai báo qua `LLMClient.chat_json(temperature=...)`.
- **Tracer**: nếu cần debug, gọi `pipelines/tracer.py` để lưu input/output stage.

## Khi thêm generator mới

1. Tạo file `generation/<name>.py` với 1 class.
2. Constructor nhận `LLMClient` + manifest/config cần thiết.
3. Method chính trả dataclass có `text` field (cho LLM-readable inject vào next stage).
4. Wire vào `pipelines/ask_pipeline.py`.
5. Optional: toggle qua `config.py` (`enable_<name>: bool = True`).
