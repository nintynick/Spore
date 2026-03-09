"""Tests for AgentCoordinator — experiment selection and context building."""


from test.conftest import make_record

from spore.agent import AgentCoordinator, CoordinatorConfig
from spore.record import Status


class TestSelectParent:
    def test_select_from_single_frontier(self, graph, keypair):
        record = make_record(keypair, val_bpb=1.0)
        graph.insert(record)

        coord = AgentCoordinator(graph)
        parent = coord.select_parent()
        assert parent is not None
        assert parent.id == record.id

    def test_select_from_empty_graph(self, graph):
        coord = AgentCoordinator(graph)
        parent = coord.select_parent()
        assert parent is None

    def test_select_respects_gpu_class(self, graph, keypair):
        h100 = make_record(keypair, val_bpb=0.90, gpu_model="H100-SXM5-80GB")
        rtx = make_record(keypair, val_bpb=0.95, gpu_model="RTX_4090")
        graph.insert(h100)
        graph.insert(rtx)

        coord = AgentCoordinator(graph)
        parent = coord.select_parent(gpu_class="RTX_4090")
        assert parent is not None
        assert parent.gpu_model == "RTX_4090"

    def test_exploit_picks_best(self, graph, keypair):
        """With exploit_ratio=1.0, always picks the best frontier."""
        config = CoordinatorConfig(exploit_ratio=1.0, explore_ratio=0.0, adaptive=False)
        coord = AgentCoordinator(graph, config)

        r1 = make_record(keypair, val_bpb=0.95, description="worse")
        r2 = make_record(keypair, val_bpb=0.90, description="better")
        graph.insert(r1)
        graph.insert(r2)

        # Run multiple times to verify deterministic
        for _ in range(10):
            parent = coord.select_parent()
            assert parent.val_bpb == 0.90

    def test_explore_prefers_under_explored(self, graph, keypair):
        """Explore mode prefers experiments with fewer children."""
        config = CoordinatorConfig(exploit_ratio=0.0, explore_ratio=1.0, adaptive=False)
        coord = AgentCoordinator(graph, config)

        # Experiment A with 5 children
        a = make_record(keypair, val_bpb=0.95, description="heavily explored")
        graph.insert(a)
        for i in range(5):
            child = make_record(
                keypair,
                parent=a.id,
                depth=1,
                val_bpb=0.96 + i * 0.001,
                status=Status.DISCARD,
                description=f"child of A {i}",
            )
            graph.insert(child)

        # Experiment B with 0 children
        b = make_record(keypair, val_bpb=0.96, description="unexplored")
        graph.insert(b)

        # Over many samples, B should be selected more often than A
        counts = {"A": 0, "B": 0}
        for _ in range(100):
            parent = coord.select_parent()
            if parent.id == a.id:
                counts["A"] += 1
            elif parent.id == b.id:
                counts["B"] += 1

        # B (0 children) should be preferred
        assert counts["B"] > counts["A"]


class TestDuplicateDetection:
    def test_identical_diff_is_duplicate(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        child = make_record(
            keypair,
            parent=parent.id,
            depth=1,
            diff="- lr=0.001\n+ lr=0.002",
            val_bpb=0.95,
        )
        graph.insert(child)

        coord = AgentCoordinator(graph)
        assert coord.is_duplicate("- lr=0.001\n+ lr=0.002", parent.id)

    def test_different_diff_is_not_duplicate(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        child = make_record(
            keypair,
            parent=parent.id,
            depth=1,
            diff="- lr=0.001\n+ lr=0.002",
            val_bpb=0.95,
        )
        graph.insert(child)

        coord = AgentCoordinator(graph)
        assert not coord.is_duplicate("- n_head=6\n+ n_head=12", parent.id)

    def test_no_siblings_means_no_duplicate(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        coord = AgentCoordinator(graph)
        assert not coord.is_duplicate("any diff", parent.id)


class TestBuildContext:
    def test_context_has_all_fields(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        coord = AgentCoordinator(graph)
        ctx = coord.build_context(parent)

        assert ctx.parent_record.id == parent.id
        assert ctx.graph_stats["total_experiments"] == 1
        assert ctx.graph_stats["frontier_size"] == 1

    def test_context_includes_siblings(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        child = make_record(
            keypair, parent=parent.id, depth=1, val_bpb=0.95, description="sibling exp"
        )
        graph.insert(child)

        coord = AgentCoordinator(graph)
        ctx = coord.build_context(parent)
        assert len(ctx.sibling) == 1
        assert ctx.sibling[0].description == "sibling exp"

    def test_context_includes_failures(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        discard = make_record(
            keypair,
            parent=parent.id,
            depth=1,
            val_bpb=1.05,
            status=Status.DISCARD,
            description="failed attempt",
        )
        graph.insert(discard)

        coord = AgentCoordinator(graph)
        ctx = coord.build_context(parent)
        assert len(ctx.recent_failure) == 1


class TestFormatPrompt:
    def test_prompt_includes_key_info(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        coord = AgentCoordinator(graph)
        ctx = coord.build_context(parent)
        prompt = coord.format_prompt(ctx)

        assert "1.000000" in prompt  # val_bpb
        assert "Current State" in prompt
        assert "Task" in prompt

    def test_prompt_shows_siblings(self, graph, keypair):
        parent = make_record(keypair, val_bpb=1.0)
        graph.insert(parent)

        child = make_record(
            keypair,
            parent=parent.id,
            depth=1,
            val_bpb=0.95,
            description="increase batch size",
        )
        graph.insert(child)

        coord = AgentCoordinator(graph)
        ctx = coord.build_context(parent)
        prompt = coord.format_prompt(ctx)

        assert "Already Tried" in prompt
        assert "increase batch size" in prompt
