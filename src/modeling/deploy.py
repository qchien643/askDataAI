"""
Deploy module - Deploy manifest với SHA1 hash tracking.

Tương đương DeployService trong WrenAI gốc
(wren-ui/src/apollo/server/services/deployService.ts).

Chức năng:
  1. Tính SHA1 hash của manifest (detect thay đổi)
  2. So sánh với hash lần deploy trước
  3. Lưu manifest JSON vào manifests/
  4. Track deploy history
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from src.modeling.mdl_schema import Manifest

logger = logging.getLogger(__name__)


class DeployResult:
    """Kết quả của 1 lần deploy."""

    def __init__(
        self,
        manifest_hash: str,
        previous_hash: str | None,
        changed: bool,
        manifest_path: str,
        timestamp: str,
    ):
        self.manifest_hash = manifest_hash
        self.previous_hash = previous_hash
        self.changed = changed
        self.manifest_path = manifest_path
        self.timestamp = timestamp

    def __repr__(self):
        status = "CHANGED" if self.changed else "NO CHANGE"
        return f"DeployResult({status}, hash={self.manifest_hash[:8]}...)"


class ManifestDeployer:
    """
    Deploy manifest: tính hash, lưu file, track changes.

    Giống logic DeployService.createMDLHash() trong WrenAI gốc:
    - Tính SHA1 hash của manifest JSON
    - So với hash lần trước
    - Nếu khác → lưu manifest mới, return changed=True (trigger re-index)
    - Nếu giống → skip, return changed=False

    Usage:
        deployer = ManifestDeployer(manifests_dir="manifests")
        result = deployer.deploy(manifest)
        if result.changed:
            # trigger re-indexing (Phase 3)
            pass
    """

    MANIFEST_FILENAME = "manifest.json"
    HASH_FILENAME = ".manifest_hash"
    HISTORY_FILENAME = "deploy_history.json"

    def __init__(self, manifests_dir: str | Path = "manifests"):
        self._manifests_dir = Path(manifests_dir)
        self._manifests_dir.mkdir(parents=True, exist_ok=True)

    def deploy(self, manifest: Manifest) -> DeployResult:
        """
        Deploy manifest mới.

        Args:
            manifest: Manifest object đã build và validate.

        Returns:
            DeployResult chứa hash, changed status, file path.
        """
        # 1. Serialize manifest → JSON string (deterministic sort)
        manifest_json = manifest.model_dump_json(indent=2)

        # 2. Tính SHA1 hash
        current_hash = self._compute_hash(manifest_json)

        # 3. Load hash lần trước
        previous_hash = self._load_previous_hash()

        # 4. So sánh
        changed = current_hash != previous_hash

        timestamp = datetime.now().isoformat()

        if changed:
            # 5. Lưu manifest JSON
            manifest_path = self._manifests_dir / self.MANIFEST_FILENAME
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write(manifest_json)

            # 6. Lưu hash mới
            self._save_hash(current_hash)

            # 7. Ghi deploy history
            self._append_history(current_hash, timestamp, previous_hash)

            logger.info(
                f"✅ Manifest deployed: hash={current_hash[:8]}... "
                f"(previous={previous_hash[:8] + '...' if previous_hash else 'None'})"
            )
        else:
            manifest_path = self._manifests_dir / self.MANIFEST_FILENAME
            logger.info(
                f"⏭️  Manifest unchanged (hash={current_hash[:8]}...), "
                f"skipping deploy."
            )

        return DeployResult(
            manifest_hash=current_hash,
            previous_hash=previous_hash,
            changed=changed,
            manifest_path=str(manifest_path),
            timestamp=timestamp,
        )

    def get_current_manifest(self) -> Manifest | None:
        """Load manifest hiện tại từ file (nếu có)."""
        manifest_path = self._manifests_dir / self.MANIFEST_FILENAME
        if not manifest_path.exists():
            return None

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return Manifest(**data)

    def get_current_hash(self) -> str | None:
        """Lấy hash của manifest hiện tại."""
        return self._load_previous_hash()

    def get_deploy_history(self) -> list[dict]:
        """Lấy lịch sử deploy."""
        history_path = self._manifests_dir / self.HISTORY_FILENAME
        if not history_path.exists():
            return []

        with open(history_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ─── Private Methods ──────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Tính SHA1 hash của content string."""
        return hashlib.sha1(content.encode("utf-8")).hexdigest()

    def _load_previous_hash(self) -> str | None:
        """Load hash từ file .manifest_hash."""
        hash_path = self._manifests_dir / self.HASH_FILENAME
        if not hash_path.exists():
            return None

        with open(hash_path, "r") as f:
            return f.read().strip()

    def _save_hash(self, hash_value: str):
        """Lưu hash vào file .manifest_hash."""
        hash_path = self._manifests_dir / self.HASH_FILENAME
        with open(hash_path, "w") as f:
            f.write(hash_value)

    def _append_history(
        self,
        hash_value: str,
        timestamp: str,
        previous_hash: str | None,
    ):
        """Ghi thêm 1 entry vào deploy history."""
        history_path = self._manifests_dir / self.HISTORY_FILENAME
        history = []

        if history_path.exists():
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)

        history.append({
            "hash": hash_value,
            "previous_hash": previous_hash,
            "timestamp": timestamp,
            "deploy_number": len(history) + 1,
        })

        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
