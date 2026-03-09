"""Tests for ArtifactStore — content-addressed storage."""




class TestArtifactStore:
    def test_put_and_get(self, store):
        data = b"hello world"
        cid = store.put(data)
        assert len(cid) == 64  # SHA-256 hex
        retrieved = store.get(cid)
        assert retrieved == data

    def test_dedup(self, store):
        data = b"same content"
        cid1 = store.put(data)
        cid2 = store.put(data)
        assert cid1 == cid2
        assert store.count() == 1

    def test_different_content_different_cid(self, store):
        cid1 = store.put(b"content_a")
        cid2 = store.put(b"content_b")
        assert cid1 != cid2
        assert store.count() == 2

    def test_has(self, store):
        cid = store.put(b"data")
        assert store.has(cid)
        assert not store.has("nonexistent" * 4)

    def test_delete(self, store):
        cid = store.put(b"to delete")
        assert store.has(cid)
        assert store.delete(cid)
        assert not store.has(cid)

    def test_delete_nonexistent(self, store):
        assert not store.delete("nonexistent" * 4)

    def test_put_file(self, store, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        cid = store.put_file(f)
        assert store.has(cid)
        content = store.get(cid, ".py")
        assert content == b"print('hello')"

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent" * 4) is None

    def test_size(self, store):
        store.put(b"aaaa")
        store.put(b"bbbbbbbb")
        assert store.size() == 12  # 4 + 8

    def test_count(self, store):
        assert store.count() == 0
        store.put(b"one")
        store.put(b"two")
        assert store.count() == 2
