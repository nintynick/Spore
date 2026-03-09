"""Content-addressed artifact storage.

Artifacts (code snapshots, model weights, logs) are stored by their SHA-256 CID.
Two identical files always map to the same path. Retrieval is by CID.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class ArtifactStore:
    def __init__(self, root: str | Path = "~/.spore/artifact"):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, extension: str = "") -> str:
        """Store raw bytes. Returns CID."""
        cid = hashlib.sha256(data).hexdigest()
        path = self._path(cid, extension)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return cid

    def put_file(self, source: str | Path) -> str:
        """Store a file by copying it. Returns CID."""
        source = Path(source)
        data = source.read_bytes()
        cid = hashlib.sha256(data).hexdigest()
        ext = source.suffix
        path = self._path(cid, ext)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path)
        return cid

    def get(self, cid: str, extension: str = "") -> bytes | None:
        """Retrieve bytes by CID. Returns None if not found."""
        path = self._path(cid, extension)
        if path.exists():
            return path.read_bytes()
        # Try without extension (scan directory)
        cid_dir = self.root / cid[:2] / cid[2:4]
        if cid_dir.exists():
            for p in cid_dir.iterdir():
                if p.stem == cid or p.name.startswith(cid):
                    return p.read_bytes()
        return None

    def get_path(self, cid: str, extension: str = "") -> Path | None:
        """Get filesystem path for a CID. Returns None if not stored."""
        path = self._path(cid, extension)
        if path.exists():
            return path
        cid_dir = self.root / cid[:2] / cid[2:4]
        if cid_dir.exists():
            for p in cid_dir.iterdir():
                if p.stem == cid or p.name.startswith(cid):
                    return p
        return None

    def has(self, cid: str) -> bool:
        """Check if a CID exists in the store."""
        return self.get_path(cid) is not None

    def delete(self, cid: str) -> bool:
        """Remove an artifact. Returns True if it existed."""
        path = self.get_path(cid)
        if path:
            path.unlink()
            return True
        return False

    def size(self) -> int:
        """Total bytes stored."""
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())

    def count(self) -> int:
        """Number of artifacts stored."""
        return sum(1 for f in self.root.rglob("*") if f.is_file())

    def _path(self, cid: str, extension: str = "") -> Path:
        """Content-addressed path: root/ab/cd/<full_cid>.ext

        First 2 chars and next 2 chars as subdirectories to avoid
        filesystem issues with too many files in one directory.
        """
        name = cid + extension if extension else cid
        return self.root / cid[:2] / cid[2:4] / name
