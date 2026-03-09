"""Spore query command — read-only graph inspection."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from .graph import ResearchGraph
from .node import SPORE_DIR

console = Console()


def _open_graph() -> ResearchGraph:
    db_path = SPORE_DIR / "db" / "graph.sqlite"
    return ResearchGraph(db_path)


def _format_param(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def register_command(cli: click.Group):
    """Register query commands on the CLI group."""

    @cli.command()
    def status():
        """Show node status, frontier, and recent experiments."""
        from .cli import ensure_initialized

        ensure_initialized()
        graph = _open_graph()

        total = graph.count()
        frontier = graph.frontier()
        recent = graph.recent(limit=10)

        console.print("\n[bold]Spore Node Status[/]")
        console.print(f"Total experiments: [cyan]{total}[/]")
        console.print(f"Frontier size: [cyan]{len(frontier)}[/]")

        if frontier:
            best = frontier[0]
            console.print(f"Best val_bpb: [green]{best.val_bpb:.6f}[/] ({best.id[:8]})")

        if recent:
            console.print("\n[bold]Recent Experiment[/]")
            table = Table(show_header=True)
            table.add_column("CID", style="cyan", width=10)
            table.add_column("val_bpb", justify="right")
            table.add_column("Status")
            table.add_column("Node", width=10)
            table.add_column("Description", max_width=40)

            for r in recent:
                status_style = {
                    "keep": "[green]keep[/]",
                    "discard": "[red]discard[/]",
                    "crash": "[yellow]crash[/]",
                }
                table.add_row(
                    r.id[:8] + "..",
                    f"{r.val_bpb:.6f}",
                    status_style.get(r.status.value, r.status.value),
                    r.node_id[:8] + "..",
                    r.description[:40],
                )
            console.print(table)

        graph.close()

    @cli.command()
    @click.option("--depth", "-d", default=50, help="Max depth to render")
    def graph(depth: int):
        """Show the research graph as an ASCII tree."""
        from .cli import ensure_initialized

        ensure_initialized()
        g = _open_graph()
        tree = g.ascii_tree(max_depth=depth)
        console.print(f"\n[bold]Research Graph[/] ({g.count()} experiments)\n")
        console.print(tree)
        g.close()

    @cli.command()
    @click.option("--gpu", "-g", default=None, help="Filter by GPU class")
    def frontier(gpu: str | None):
        """Show the current frontier (best unbeaten experiments)."""
        from .cli import ensure_initialized

        ensure_initialized()
        g = _open_graph()

        result = g.frontier(gpu_class=gpu)
        if not result:
            console.print("No frontier experiments found.")
            g.close()
            return

        console.print(f"\n[bold]Frontier[/] ({len(result)} experiments)")
        if gpu:
            console.print(f"GPU filter: {gpu}")

        table = Table(show_header=True)
        table.add_column("CID", style="cyan", width=10)
        table.add_column("val_bpb", justify="right", style="green")
        table.add_column("Depth", justify="right")
        table.add_column("GPU")
        table.add_column("Step", justify="right")
        table.add_column("Param", justify="right")
        table.add_column("Description", max_width=40)

        for r in result:
            table.add_row(
                r.id[:8] + "..",
                f"{r.val_bpb:.6f}",
                str(r.depth),
                r.gpu_model,
                str(r.num_steps),
                _format_param(r.num_params),
                r.description[:40],
            )
        console.print(table)
        g.close()

    @cli.command()
    def info():
        """Show node identity and config."""
        from .cli import ensure_initialized
        from .node import NodeConfig

        node_id = ensure_initialized()
        config = NodeConfig.load()

        console.print("\n[bold]Node Info[/]")
        console.print(f"  Node ID:     [cyan]{node_id}[/]")
        console.print(f"  Listen:      {config.host}:{config.port}")
        console.print(f"  Data dir:    {config.data_dir}")
        console.print(f"  Peer count:  {len(config.peer)}")

        g = _open_graph()
        console.print(f"  Experiment:  {g.count()}")
        f = g.frontier()
        if f:
            console.print(f"  Best val_bpb: [green]{f[0].val_bpb:.6f}[/]")
        g.close()
