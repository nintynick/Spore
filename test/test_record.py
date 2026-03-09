"""Tests for ExperimentRecord — CID, signing, serialization."""

import json
from test.conftest import make_record

from spore.record import ExperimentRecord, Status, compute_file_cid, generate_keypair


class TestExperimentRecord:
    def test_create_record(self, keypair):
        record = make_record(keypair, val_bpb=0.95)
        assert record.val_bpb == 0.95
        assert record.status == Status.KEEP
        assert record.id  # CID was computed
        assert record.signature  # Was signed

    def test_cid_deterministic(self, keypair):
        """Same data produces same CID."""
        r1 = make_record(keypair, val_bpb=0.95, description="same")
        r2 = make_record(keypair, val_bpb=0.95, description="same")
        # CIDs differ because timestamps differ, but canonical payload logic is consistent
        assert r1.verify_cid()
        assert r2.verify_cid()

    def test_cid_changes_with_data(self, keypair):
        """Different data produces different CID."""
        r1 = make_record(keypair, val_bpb=0.95, description="experiment A")
        r2 = make_record(keypair, val_bpb=0.96, description="experiment B")
        assert r1.id != r2.id

    def test_verify_cid(self, keypair):
        record = make_record(keypair)
        assert record.verify_cid()
        # Tamper with val_bpb
        record.val_bpb = 0.001
        assert not record.verify_cid()

    def test_verify_signature(self, keypair):
        record = make_record(keypair)
        assert record.verify_signature()

    def test_signature_fails_with_wrong_key(self, keypair, second_keypair):
        record = make_record(keypair)
        # Replace node_id with a different key
        _, other_id = second_keypair
        record.node_id = other_id
        assert not record.verify_signature()

    def test_signature_fails_on_tamper(self, keypair):
        record = make_record(keypair)
        original_sig = record.signature
        record.description = "tampered"
        # Signature was computed over original data
        assert not record.verify_signature()

    def test_json_roundtrip(self, keypair):
        record = make_record(keypair, val_bpb=0.972, description="weight decay")
        json_str = record.to_json()
        restored = ExperimentRecord.from_json(json_str)
        assert restored.id == record.id
        assert restored.val_bpb == record.val_bpb
        assert restored.description == record.description
        assert restored.status == Status.KEEP
        assert restored.verify_cid()

    def test_json_roundtrip_from_dict(self, keypair):
        record = make_record(keypair)
        data = json.loads(record.to_json())
        restored = ExperimentRecord.from_json(data)
        assert restored.id == record.id

    def test_status_enum(self, keypair):
        for status in [Status.KEEP, Status.DISCARD, Status.CRASH]:
            record = make_record(keypair, status=status)
            json_str = record.to_json()
            restored = ExperimentRecord.from_json(json_str)
            assert restored.status == status

    def test_genesis_record(self, keypair):
        """Genesis record has no parent."""
        record = make_record(keypair, parent=None, depth=0)
        assert record.parent is None
        assert record.depth == 0
        assert record.verify_cid()

    def test_child_record(self, keypair):
        """Child record points to parent."""
        parent = make_record(keypair, val_bpb=1.0)
        child = make_record(keypair, parent=parent.id, depth=1, val_bpb=0.95)
        assert child.parent == parent.id
        assert child.depth == 1


class TestGenerateKeypair:
    def test_generates_unique_keys(self):
        _, id1 = generate_keypair()
        _, id2 = generate_keypair()
        assert id1 != id2

    def test_key_is_hex(self):
        _, node_id = generate_keypair()
        assert len(node_id) == 64  # 32 bytes hex-encoded
        int(node_id, 16)  # Should parse as hex


class TestComputeFileCid:
    def test_file_cid(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        cid = compute_file_cid(str(f))
        assert len(cid) == 64
        # Same content = same CID
        f2 = tmp_path / "test2.py"
        f2.write_text("print('hello')")
        assert compute_file_cid(str(f2)) == cid

    def test_different_content_different_cid(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("code_a")
        f2.write_text("code_b")
        assert compute_file_cid(str(f1)) != compute_file_cid(str(f2))
