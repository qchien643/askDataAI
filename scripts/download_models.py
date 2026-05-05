"""
Pre-download local copies of HuggingFace models used by askDataAI.

Currently downloads:
- leolee99/PIGuard (~736MB) — Stage 0 prompt injection guardrail.

Models are saved into models/<name>/ at the repo root. Once downloaded,
askdataai/security/pi_guardrail.py loads them with local_files_only=True
so the program no longer touches the network on subsequent runs.

Usage:
    python scripts/download_models.py
    python scripts/download_models.py --force            # overwrite existing
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MODELS = {
    "piguard": {
        "repo_id": "leolee99/PIGuard",
        "subfolder": "piguard",
    },
}


def download_one(
    repo_id: str,
    target_dir: Path,
    *,
    force: bool = False,
) -> bool:
    """Download / copy a model snapshot into target_dir.

    Returns True on success.
    """
    if target_dir.exists() and any(target_dir.iterdir()):
        if not force:
            print(f"[SKIP] {target_dir} already populated (use --force to redownload)")
            return True
        print(f"[..] Removing existing {target_dir}")
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[!!] huggingface_hub not installed. Run: pip install huggingface_hub", file=sys.stderr)
        return False

    print(f"[..] Fetching {repo_id} -> {target_dir}")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
        )
    except Exception as e:
        print(f"[!!] Download failed for {repo_id}: {e}", file=sys.stderr)
        return False

    files = sum(1 for _ in target_dir.rglob("*") if _.is_file())
    print(f"[OK] {repo_id}: {files} files in {target_dir}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if local copy exists",
    )
    parser.add_argument(
        "--only",
        choices=list(MODELS.keys()),
        help="Download a single model by name",
    )
    args = parser.parse_args()

    targets = MODELS if args.only is None else {args.only: MODELS[args.only]}

    failures = []
    for name, spec in targets.items():
        target = REPO_ROOT / "models" / spec["subfolder"]
        ok = download_one(spec["repo_id"], target, force=args.force)
        if not ok:
            failures.append(name)

    if failures:
        print(f"\n[FAIL] {len(failures)} model(s) failed: {', '.join(failures)}")
        return 1

    print("\n[Done] All models ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
