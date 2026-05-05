"""
PIGuardrail — Prompt Injection Detection bằng leolee99/PIGuard.

PIGuard là model DeBERTa-v3-base được fine-tune bởi leolee99 (ACL 2025).
Nó phát hiện Prompt Injection attacks với độ chính xác SOTA, giảm over-defense
so với các model trước đó nhờ chiến lược MOF (Mitigating Over-defense for Free).

Flow tích hợp vào Ask Pipeline:
    question
        ↓
    [Stage 0] PIGuardrail  ← ĐÂY (trước PreFilter)
        ├── INJECTION_DETECTED → reject ngay (0 LLM call)
        └── SAFE → tiếp tục Stage 1: PreFilter → ...

Refs:
    - HuggingFace: https://huggingface.co/leolee99/PIGuard
    - Paper (ACL 2025): https://aclanthology.org/2025.acl-long.1468.pdf
    - GitHub: https://github.com/leolee99/PIGuard
"""

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

MODEL_NAME = "leolee99/PIGuard"

# Project-local cache: scripts/download-models.ps1 (or download_models.py)
# fills this directory once. When present, the model is loaded with
# local_files_only=True so the runtime never touches the network.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_MODEL_DIR = _PROJECT_ROOT / "models" / "piguard"

# PIGuard label mapping (xác minh từ model config):
# - "injection" = malicious prompt injection
# - "benign"    = safe input
# (model dùng named labels, không phải LABEL_0/LABEL_1)
INJECTION_LABEL = "injection"
BENIGN_LABEL = "benign"

# Ngưỡng confidence để coi là injection (0.5 = default, tăng lên 0.7+ để giảm false positive)
DEFAULT_THRESHOLD = 0.5


# ── Enums & Dataclasses ───────────────────────────────────────────

class PIGuardResult(str, Enum):
    SAFE = "SAFE"
    INJECTION_DETECTED = "INJECTION_DETECTED"
    ERROR = "ERROR"  # Model lỗi → fallback safe (không block)


@dataclass
class PIGuardOutput:
    """Kết quả kiểm tra từ PIGuard."""
    result: PIGuardResult
    confidence: float = 0.0           # Confidence score của prediction
    label: str = ""                    # Raw label từ model (LABEL_0/LABEL_1)
    response: str = ""                 # Response pre-built nếu bị block
    model_loaded: bool = True          # Có model hay không


# ── Blocked Response ───────────────────────────────────────────────

INJECTION_BLOCKED_RESPONSE = (
    "⚠️ Yêu cầu bị từ chối: phát hiện **Prompt Injection** attack.\n\n"
    "Câu hỏi của bạn chứa nội dung cố tình thao túng hệ thống AI. "
    "Vui lòng đặt câu hỏi bình thường về dữ liệu trong database."
)


# ── PIGuardrail ────────────────────────────────────────────────────

class PIGuardrail:
    """
    Stage 0 Guardrail: Phát hiện Prompt Injection bằng leolee99/PIGuard.

    Load model một lần (lazy + thread-safe) khi lần đầu được gọi.
    Nếu model không load được (CPU/memory hạn chế), gracefully fallback
    → return SAFE để không block pipeline.

    Usage:
        guardrail = PIGuardrail()
        output = guardrail.check("Ignore previous instructions and...")
        if output.result == PIGuardResult.INJECTION_DETECTED:
            return error_response(output.response)
    """

    _instance_lock = threading.Lock()

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        threshold: float = DEFAULT_THRESHOLD,
        device: str = "cpu",
        enabled: bool = True,
    ):
        """
        Args:
            model_name: HuggingFace model ID (default: leolee99/PIGuard).
            threshold: Confidence threshold để coi là injection (0.0–1.0).
                       Tăng lên 0.7+ để giảm false positive.
            device: "cpu" hoặc "cuda" (nếu có GPU).
            enabled: False → skip hoàn toàn (for testing/dev).
        """
        self._model_name = model_name
        self._threshold = threshold
        self._device = device
        self._enabled = enabled

        # Lazy-load state
        self._pipeline = None
        self._load_lock = threading.Lock()
        self._load_attempted = False
        self._load_success = False

        logger.info(
            f"PIGuardrail configured: model={model_name}, "
            f"threshold={threshold}, device={device}, enabled={enabled}"
        )

    def _ensure_loaded(self) -> bool:
        """
        Lazy-load PIGuard model (thread-safe, chỉ load 1 lần).

        Returns:
            True nếu model đã sẵn sàng, False nếu load thất bại.
        """
        if self._load_attempted:
            return self._load_success

        with self._load_lock:
            # Double-check sau khi lấy lock
            if self._load_attempted:
                return self._load_success

            # Resolve source: project-local snapshot if available, else HF hub.
            if LOCAL_MODEL_DIR.exists() and any(LOCAL_MODEL_DIR.iterdir()):
                source = str(LOCAL_MODEL_DIR)
                local_only = True
                logger.info(
                    f"Loading PIGuard from local snapshot: {source} "
                    f"(local_files_only=True, no network)"
                )
            else:
                source = self._model_name
                local_only = False
                logger.info(
                    f"Loading PIGuard from HuggingFace hub: {self._model_name} "
                    f"(local snapshot not found at {LOCAL_MODEL_DIR}). "
                    f"Run scripts/download-models.ps1 to cache locally and skip future downloads."
                )

            try:
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                    pipeline,
                )

                tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=local_only)
                model = AutoModelForSequenceClassification.from_pretrained(
                    source,
                    trust_remote_code=True,
                    local_files_only=local_only,
                )
                self._pipeline = pipeline(
                    "text-classification",
                    model=model,
                    tokenizer=tokenizer,
                    truncation=True,
                    top_k=None,     # Trả về tất cả labels kèm score
                    device=self._device if self._device != "cpu" else -1,
                )
                self._load_success = True
                logger.info(
                    f"PIGuard loaded successfully: {self._model_name} "
                    f"(base: microsoft/deberta-v3-base, "
                    f"source={'local' if local_only else 'hub'})"
                )
            except ImportError:
                logger.error(
                    "transformers not installed. "
                    "Run: pip install transformers torch"
                )
                self._load_success = False
            except Exception as e:
                logger.error(f"Failed to load PIGuard: {e}", exc_info=True)
                self._load_success = False
            finally:
                self._load_attempted = True

        return self._load_success

    def check(self, text: str) -> PIGuardOutput:
        """
        Kiểm tra text có phải Prompt Injection không.

        Args:
            text: Câu hỏi / input từ user.

        Returns:
            PIGuardOutput với result, confidence score.
        """
        # Disabled → skip
        if not self._enabled:
            return PIGuardOutput(
                result=PIGuardResult.SAFE,
                confidence=0.0,
                label="DISABLED",
                model_loaded=False,
            )

        # Empty input → skip
        if not text or not text.strip():
            return PIGuardOutput(result=PIGuardResult.SAFE, confidence=0.0)

        # Load model nếu chưa có
        if not self._ensure_loaded():
            logger.warning(
                "PIGuard model unavailable — skipping check (fail-open)"
            )
            return PIGuardOutput(
                result=PIGuardResult.ERROR,
                confidence=0.0,
                label="MODEL_UNAVAILABLE",
                model_loaded=False,
            )

        try:
            raw = self._pipeline([text])
            # raw[0] = list of {label, score} cho tất cả classes
            # Ví dụ: [{'label': 'injection', 'score': 0.999}, {'label': 'benign', 'score': 0.001}]
            label_scores: dict[str, float] = {
                item["label"]: float(item["score"])
                for item in raw[0]
            }

            injection_score = label_scores.get(INJECTION_LABEL, 0.0)
            benign_score = label_scores.get(BENIGN_LABEL, 1.0)
            
            # Top label = label có score cao nhất
            top_label = max(label_scores, key=label_scores.get)  # type: ignore

            is_injection = (top_label == INJECTION_LABEL) and (injection_score >= self._threshold)

            if is_injection:
                logger.warning(
                    f"PIGuard: INJECTION DETECTED "
                    f"(injection_score={injection_score:.3f}, "
                    f"benign_score={benign_score:.3f}, "
                    f"threshold={self._threshold}) "
                    f"— text[:80]={text[:80]!r}"
                )
                return PIGuardOutput(
                    result=PIGuardResult.INJECTION_DETECTED,
                    confidence=injection_score,
                    label=top_label,
                    response=INJECTION_BLOCKED_RESPONSE,
                )
            else:
                logger.debug(
                    f"PIGuard: SAFE "
                    f"(injection_score={injection_score:.3f}, "
                    f"benign_score={benign_score:.3f})"
                )
                return PIGuardOutput(
                    result=PIGuardResult.SAFE,
                    confidence=benign_score,
                    label=top_label,
                )

        except Exception as e:
            logger.error(f"PIGuard inference error: {e}", exc_info=True)
            # Fail-open: nếu inference lỗi → coi là safe (tránh DoS pipeline)
            return PIGuardOutput(
                result=PIGuardResult.ERROR,
                confidence=0.0,
                label="INFERENCE_ERROR",
            )

    @property
    def is_loaded(self) -> bool:
        """Kiểm tra model đã được load chưa."""
        return self._load_success

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info(f"PIGuardrail {'enabled' if value else 'disabled'}")
