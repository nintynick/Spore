"""Signed control-plane events for challenge, verification, and dispute gossip."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field

from nacl.encoding import HexEncoder
from nacl.signing import SigningKey, VerifyKey


@dataclass
class SignedControlEvent:
    type: str
    payload: dict
    node_id: str
    timestamp: int = field(default_factory=lambda: int(time.time()))
    signature: str = ""
    id: str = ""
    version: int = 1

    def canonical_payload(self) -> dict:
        data = asdict(self)
        data.pop("id")
        data.pop("signature")
        return data

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

    def compute_id(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def sign(self, signing_key: SigningKey) -> None:
        self.signature = signing_key.sign(
            self.canonical_bytes(), encoder=HexEncoder
        ).signature.decode("ascii")
        self.id = self.compute_id()

    def verify_signature(self) -> bool:
        try:
            verify_key = VerifyKey(bytes.fromhex(self.node_id))
            verify_key.verify(self.canonical_bytes(), bytes.fromhex(self.signature))
            return True
        except Exception:
            return False

    def verify_id(self) -> bool:
        return self.id == self.compute_id()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: str | dict) -> SignedControlEvent:
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**dict(data))
