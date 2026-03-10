"""CLI commands for the Spore token incentive layer."""

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
    def token():
        """Manage $SPORE and $xSPORE tokens."""
        pass

    @token.command("balance")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_balance(data_dir: str | None):
        """Show token balances for the local node."""
        node = _make_node(data_dir)
        summary = node.token.node_summary(node.node_id)

        table = Table(title="Token Balance", show_header=False, border_style="cyan")
        table.add_column("Key", style="dim")
        table.add_column("Value")
        table.add_row("Node", f"[cyan]{node.node_id[:16]}...[/]")
        table.add_row("$SPORE", f"[green]{summary['spore_balance']:.2f}[/]")
        table.add_row("$xSPORE", f"[yellow]{summary['xspore_balance']:.2f}[/]")
        table.add_row("Staked", f"[red]{summary['staked']:.2f}[/]")
        table.add_row("Pending Rewards", str(summary["pending_rewards"]))
        table.add_row("Claimable $SPORE", f"[green]{summary['claimable_spore']:.2f}[/]")
        table.add_row("Claim Fee", f"[dim]{summary['claim_fee']:.2f}[/]")
        console.print(table)
        _close_node(node)

    @token.command("stake")
    @click.argument("amount", type=float)
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_stake(amount: float, data_dir: str | None):
        """Stake $SPORE to participate in the protocol."""
        node = _make_node(data_dir)
        if node.token.add_stake(node.node_id, amount):
            console.print(f"Staked [green]{amount:.2f} $SPORE[/].")
            console.print(
                f"Total staked: [green]{node.token.stake_amount(node.node_id):.2f}[/]"
            )
        else:
            console.print("[red]Insufficient $SPORE balance to stake.[/]")
        _close_node(node)

    @token.command("unstake")
    @click.argument("amount", type=float)
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_unstake(amount: float, data_dir: str | None):
        """Unstake $SPORE."""
        node = _make_node(data_dir)
        if node.token.remove_stake(node.node_id, amount):
            console.print(f"Unstaked [green]{amount:.2f} $SPORE[/].")
        else:
            console.print("[red]Insufficient staked amount.[/]")
        _close_node(node)

    @token.command("claim")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_claim(data_dir: str | None):
        """Claim matured $xSPORE → $SPORE rewards."""
        node = _make_node(data_dir)
        result = node.token.claim_rewards(node.node_id)
        if result is None:
            console.print("Nothing to claim.")
        else:
            console.print(f"Burned [yellow]{result.xspore_burned:.2f} $xSPORE[/]")
            console.print(f"Minted [green]{result.spore_minted:.2f} $SPORE[/]")
            if result.fee_paid > 0:
                console.print(
                    f"Fee paid: [dim]{result.fee_paid:.2f}[/] "
                    f"(redistributed to patient holders)"
                )
        _close_node(node)

    @token.command("leaderboard")
    @click.option("--limit", "-n", default=20, help="Number of entries")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_leaderboard(limit: int, data_dir: str | None):
        """Show the token leaderboard."""
        node = _make_node(data_dir)
        entries = node.token.leaderboard(limit)
        if not entries:
            console.print("No token data yet.")
            _close_node(node)
            return

        table = Table(title="Token Leaderboard", border_style="cyan")
        table.add_column("#", style="dim")
        table.add_column("Node")
        table.add_column("$xSPORE", justify="right")
        table.add_column("$SPORE", justify="right")
        table.add_column("Staked", justify="right")

        for i, entry in enumerate(entries, 1):
            table.add_row(
                str(i),
                f"[cyan]{entry['node_id'][:12]}...[/]",
                f"[yellow]{entry['xspore']:.1f}[/]",
                f"[green]{entry['spore']:.1f}[/]",
                f"{entry['staked']:.1f}",
            )
        console.print(table)
        _close_node(node)

    @token.command("stats")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_stats(data_dir: str | None):
        """Show global token statistics."""
        node = _make_node(data_dir)
        stats = node.token.global_stats()

        table = Table(title="Global Token Stats", show_header=False, border_style="cyan")
        table.add_column("Key", style="dim")
        table.add_column("Value")
        table.add_row("Total $SPORE Minted", f"{stats['total_spore_minted']:,.2f}")
        table.add_row("Total $SPORE Burned", f"{stats['total_spore_burned']:,.2f}")
        table.add_row("Circulating $SPORE", f"[green]{stats['circulating_spore']:,.2f}[/]")
        table.add_row("Max Supply", f"{stats['max_supply']:,}")
        table.add_row("Genesis Experiments", str(stats["genesis_experiments"]))
        table.add_row(
            "Epoch",
            "[yellow]Genesis[/]" if stats["in_genesis_epoch"] else "Post-genesis",
        )
        console.print(table)
        _close_node(node)

    @token.command("history")
    @click.option("--limit", "-n", default=20, help="Number of events")
    @click.option("--data-dir", "-d", default=None, help="Data directory")
    def token_history(limit: int, data_dir: str | None):
        """Show recent token events for the local node."""
        node = _make_node(data_dir)
        events = node.token.event_history(node.node_id, limit)
        if not events:
            console.print("No token events yet.")
            _close_node(node)
            return

        table = Table(title="Token Event History", border_style="cyan")
        table.add_column("Kind")
        table.add_column("Amount", justify="right")
        table.add_column("Detail", style="dim")

        for ev in events:
            kind_color = "green" if "mint" in ev["kind"] or "reward" in ev["kind"] else "red"
            table.add_row(
                f"[{kind_color}]{ev['kind']}[/]",
                f"{ev['amount']:.2f}",
                ev.get("detail", ""),
            )
        console.print(table)
        _close_node(node)
