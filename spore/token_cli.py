"""CLI commands for the Mycelia fungal intelligence network."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .node import SPORE_DIR, NodeConfig, SporeNode

console = Console()


def _make_node(data_dir: str | None) -> SporeNode:
    data_path = Path(data_dir).expanduser() if data_dir else SPORE_DIR
    config = NodeConfig.load(data_path / "config.toml")
    config.data_dir = str(data_path)
    return SporeNode(config)


def _close_node(node: SporeNode):
    node.graph.close()
    node.profile.close()
    node.reputation.close()
    node.control.close()
    node.token.close()


def register_command(cli_group):
    @cli_group.group()
    def fungus():
        """Manage $MYCO and $HYPHA tokens — the fungal economy."""
        pass

    # Keep backward compat alias
    @cli_group.group(name="token", hidden=True)
    def token_alias():
        """Alias for 'fungus'."""
        pass

    @fungus.command("balance")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_balance(data_dir: str | None):
        """Show mycelium balances for the local cultivator."""
        node = _make_node(data_dir)
        summary = node.token.node_summary(node.node_id)

        table = Table(title="Mycelium Balance", show_header=False, border_style="green")
        table.add_column("Key", style="dim")
        table.add_column("Value")
        table.add_row("Cultivator", f"[cyan]{node.node_id[:16]}...[/]")
        table.add_row("$MYCO", f"[green]{summary['myco_balance']:.2f}[/]")
        table.add_row("$HYPHA", f"[yellow]{summary['hypha_balance']:.2f}[/]")
        table.add_row("Inoculated", f"[red]{summary['inoculated']:.2f}[/]")
        table.add_row("Fruiting Bodies", str(summary["fruiting_bodies"]))
        table.add_row("Harvestable $MYCO", f"[green]{summary['harvestable_myco']:.2f}[/]")
        table.add_row("Decomposition", f"[dim]{summary['decomposition_fee']:.2f}[/]")
        console.print(table)
        _close_node(node)

    @fungus.command("inoculate")
    @click.argument("amount", type=float)
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_inoculate(amount: float, data_dir: str | None):
        """Inoculate $MYCO into the substrate (stake to participate)."""
        node = _make_node(data_dir)
        if node.token.inoculate(node.node_id, amount):
            console.print(f"Inoculated [green]{amount:.2f} $MYCO[/] into the substrate.")
            console.print(
                f"Total inoculation: [green]{node.token.inoculation_amount(node.node_id):.2f}[/]"
            )
        else:
            console.print("[red]Insufficient $MYCO to inoculate.[/]")
        _close_node(node)

    @fungus.command("extract")
    @click.argument("amount", type=float)
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_extract(amount: float, data_dir: str | None):
        """Extract $MYCO from the substrate (unstake)."""
        node = _make_node(data_dir)
        if node.token.extract(node.node_id, amount):
            console.print(f"Extracted [green]{amount:.2f} $MYCO[/] from the substrate.")
        else:
            console.print("[red]Insufficient inoculation to extract.[/]")
        _close_node(node)

    @fungus.command("harvest")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_harvest(data_dir: str | None):
        """Harvest matured fruiting bodies: $HYPHA -> $MYCO."""
        node = _make_node(data_dir)
        result = node.token.harvest(node.node_id)
        if result is None:
            console.print("Nothing to harvest. The mycelium needs more time.")
        else:
            console.print(f"Consumed [yellow]{result.hypha_consumed:.2f} $HYPHA[/]")
            console.print(f"Yielded  [green]{result.myco_yielded:.2f} $MYCO[/]")
            if result.decomposed > 0:
                console.print(
                    f"Decomposed: [dim]{result.decomposed:.2f}[/] "
                    f"(recycled as nutrients to patient cultivators)"
                )
        _close_node(node)

    @fungus.command("canopy")
    @click.option("--limit", "-n", default=20, help="Number of entries")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_canopy(limit: int, data_dir: str | None):
        """Show the canopy — top cultivators by $HYPHA contribution."""
        node = _make_node(data_dir)
        entries = node.token.leaderboard(limit)
        if not entries:
            console.print("The forest floor is empty. No cultivators yet.")
            _close_node(node)
            return

        table = Table(title="The Canopy", border_style="green")
        table.add_column("#", style="dim")
        table.add_column("Cultivator")
        table.add_column("$HYPHA", justify="right")
        table.add_column("$MYCO", justify="right")
        table.add_column("Inoculated", justify="right")

        for i, entry in enumerate(entries, 1):
            table.add_row(
                str(i),
                f"[cyan]{entry['node_id'][:12]}...[/]",
                f"[yellow]{entry['hypha']:.1f}[/]",
                f"[green]{entry['myco']:.1f}[/]",
                f"{entry['inoculated']:.1f}",
            )
        console.print(table)
        _close_node(node)

    @fungus.command("substrate")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_substrate(data_dir: str | None):
        """Show global substrate statistics."""
        node = _make_node(data_dir)
        stats = node.token.global_stats()

        table = Table(title="Substrate Health", show_header=False, border_style="green")
        table.add_column("Key", style="dim")
        table.add_column("Value")
        table.add_row("Total $MYCO Grown", f"{stats['total_myco_minted']:,.2f}")
        table.add_row("Total $MYCO Composted", f"{stats['total_myco_composted']:,.2f}")
        table.add_row("Circulating $MYCO", f"[green]{stats['circulating_myco']:,.2f}[/]")
        table.add_row("Max Supply", f"{stats['max_supply']:,}")
        table.add_row("Flush Count", str(stats["flush_count"]))
        table.add_row(
            "Epoch",
            "[yellow]First Flush[/]" if stats["in_first_flush"] else "Mature Growth",
        )
        console.print(table)
        _close_node(node)

    @fungus.command("log")
    @click.option("--limit", "-n", default=20, help="Number of events")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def fungus_log(limit: int, data_dir: str | None):
        """Show recent mycelium events for the local cultivator."""
        node = _make_node(data_dir)
        events = node.token.event_history(node.node_id, limit)
        if not events:
            console.print("No mycelium events yet. The network is dormant.")
            _close_node(node)
            return

        table = Table(title="Mycelium Activity Log", border_style="green")
        table.add_column("Event")
        table.add_column("Amount", justify="right")
        table.add_column("Detail", style="dim")

        for ev in events:
            kind = ev["kind"]
            if "growth" in kind or "extend" in kind or "harvest" in kind:
                color = "green"
            elif "blight" in kind or "wither" in kind or "compost" in kind:
                color = "red"
            else:
                color = "yellow"
            table.add_row(
                f"[{color}]{kind}[/]",
                f"{ev['amount']:.2f}",
                ev.get("detail", ""),
            )
        console.print(table)
        _close_node(node)
