"""Tests for ResearchGraph — DAG operations, frontier, queries."""

from test.conftest import make_record

import pytest

from spore.record import Status


class TestGraphInsert:
    def test_insert_genesis(self, graph, keypair):
        record = make_record(keypair, val_bpb=1.0)
        assert graph.insert(record)
        assert graph.count() == 1

    def test_dedup_by_cid(self, graph, keypair):
        record = make_record(keypair, val_bpb=1.0)
        assert graph.insert(record)
        assert not graph.insert(record)  # Duplicate
        assert graph.count() == 1

    def test_insert_rejects_invalid_cid(self, graph, keypair):
        record = make_record(keypair)
        record.val_bpb = 0.001  # Tamper without re-signing
        with pytest.raises(ValueError, match="CID mismatch"):
            graph.insert(record)

    def test_insert_rejects_unsigned(self, graph, keypair):
        sk, node_id = keypair
        from spore.record import ExperimentRecord

        record = ExperimentRecord(
            parent=None,
            depth=0,
            code_cid="a" * 64,
            diff="",
            dataset_cid="d",
            prepare_cid="p",
            time_budget=300,
            val_bpb=1.0,
            peak_vram_mb=0,
            num_steps=0,
            num_params=0,
            status=Status.KEEP,
            description="",
            hypothesis="",
            agent_model="test",
            gpu_model="test",
            cuda_version="",
            torch_version="",
            node_id=node_id,
        )
        with pytest.raises(ValueError, match="no CID"):
            graph.insert(record)


class TestGraphQuery:
    def test_get_by_cid(self, graph, keypair):
        record = make_record(keypair)
        graph.insert(record)
        retrieved = graph.get(record.id)
        assert retrieved is not None
        assert retrieved.id == record.id
        assert retrieved.val_bpb == record.val_bpb

    def test_get_nonexistent(self, graph):
        assert graph.get("nonexistent") is None

    def test_children(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        child1 = make_record(keypair, parent=parent.id, depth=1, val_bpb=0.95)
        child2 = make_record(
            keypair,
            parent=parent.id,
            depth=1,
            val_bpb=0.98,
            description="different child",
        )
        graph.insert(child1)
        graph.insert(child2)

        children = graph.children(parent.id)
        assert len(children) == 2

    def test_ancestors(self, graph, keypair):
        g = make_record(keypair, val_bpb=1.0, description="genesis")
        graph.insert(g)

        c1 = make_record(
            keypair, parent=g.id, depth=1, val_bpb=0.95, description="child"
        )
        graph.insert(c1)

        c2 = make_record(
            keypair, parent=c1.id, depth=2, val_bpb=0.90, description="grandchild"
        )
        graph.insert(c2)

        chain = graph.ancestors(c2.id)
        assert len(chain) == 3
        assert chain[0].description == "grandchild"
        assert chain[1].description == "child"
        assert chain[2].description == "genesis"

    def test_recent(self, graph, keypair):
        for i in range(5):
            r = make_record(keypair, val_bpb=1.0 - i * 0.01, description=f"exp {i}")
            graph.insert(r)
        recent = graph.recent(limit=3)
        assert len(recent) == 3

    def test_by_node(self, graph, keypair, second_keypair):
        r1 = make_record(keypair, description="from node 1")
        r2 = make_record(second_keypair, description="from node 2")
        graph.insert(r1)
        graph.insert(r2)

        _, node_id_1 = keypair
        results = graph.by_node(node_id_1)
        assert len(results) == 1
        assert results[0].description == "from node 1"


class TestFrontier:
    def test_single_experiment_is_frontier(self, graph, keypair):
        record = make_record(keypair, val_bpb=1.0)
        graph.insert(record)
        frontier = graph.frontier()
        assert len(frontier) == 1
        assert frontier[0].id == record.id

    def test_beaten_experiment_leaves_frontier(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        child = make_record(keypair, parent=parent.id, depth=1, val_bpb=0.95)
        graph.insert(child)

        frontier = graph.frontier()
        assert len(frontier) == 1
        assert frontier[0].id == child.id  # Child is the frontier, not parent

    def test_discard_doesnt_beat_parent(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        discard = make_record(
            keypair, parent=parent.id, depth=1, val_bpb=1.05, status=Status.DISCARD
        )
        graph.insert(discard)

        frontier = graph.frontier()
        assert len(frontier) == 1
        assert frontier[0].id == parent.id  # Parent still on frontier

    def test_multiple_branches(self, graph, keypair):
        genesis = make_record(keypair, val_bpb=1.0, description="genesis")
        graph.insert(genesis)

        # Branch A: improves
        a = make_record(
            keypair, parent=genesis.id, depth=1, val_bpb=0.95, description="branch A"
        )
        graph.insert(a)

        # Branch B: different improvement from genesis
        b = make_record(
            keypair, parent=genesis.id, depth=1, val_bpb=0.97, description="branch B"
        )
        graph.insert(b)

        frontier = graph.frontier()
        # Both A and B are frontier (genesis is beaten by both)
        assert len(frontier) == 2
        cids = {f.id for f in frontier}
        assert a.id in cids
        assert b.id in cids

    def test_gpu_class_filter(self, graph, keypair):
        r1 = make_record(keypair, val_bpb=0.95, gpu_model="H100-SXM5-80GB")
        r2 = make_record(keypair, val_bpb=0.97, gpu_model="RTX_4090")
        graph.insert(r1)
        graph.insert(r2)

        h100_frontier = graph.frontier(gpu_class="H100-SXM5-80GB")
        assert len(h100_frontier) == 1
        assert h100_frontier[0].gpu_model == "H100-SXM5-80GB"

    def test_deep_chain(self, graph, keypair):
        """Frontier is the leaf of a deep chain."""
        parent_id = None
        last_record = None
        for i in range(10):
            r = make_record(
                keypair,
                parent=parent_id,
                depth=i,
                val_bpb=1.0 - i * 0.01,
                description=f"depth {i}",
            )
            graph.insert(r)
            parent_id = r.id
            last_record = r

        frontier = graph.frontier()
        assert len(frontier) == 1
        assert frontier[0].id == last_record.id


class TestAsciiTree:
    def test_empty_graph(self, graph):
        assert graph.ascii_tree() == "(empty graph)"

    def test_single_node(self, graph, keypair):
        record = make_record(keypair, val_bpb=1.0, description="genesis")
        graph.insert(record)
        tree = graph.ascii_tree()
        assert "genesis" in tree
        assert record.id[:8] in tree

    def test_tree_structure(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0, description="parent")
        graph.insert(parent)

        child = make_record(
            keypair, parent=parent.id, depth=1, val_bpb=0.95, description="child"
        )
        graph.insert(child)

        tree = graph.ascii_tree()
        assert "parent" in tree
        assert "child" in tree


class TestMarkVerified:
    def test_mark_verified(self, graph, keypair):
        record = make_record(keypair)
        graph.insert(record)
        graph.mark_verified(record.id, True)
        # Verify the flag was set (query the DB directly)
        row = graph.conn.execute(
            "SELECT verified FROM experiment WHERE id = ?", (record.id,)
        ).fetchone()
        assert row["verified"] == 1
