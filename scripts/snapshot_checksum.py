import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Return the SHA256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_fingerprint(manifest: dict[str, Any]) -> str:
    """
    Return a stable SHA256 fingerprint for a manifest dictionary.

    The fingerprint intentionally excludes the fingerprint field itself and
    hashes canonical JSON so whitespace and key order do not affect the result.
    """
    manifest_copy = {
        key: value for key, value in manifest.items() if key != "snapshot_fingerprint"
    }
    canonical = json.dumps(
        manifest_copy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
