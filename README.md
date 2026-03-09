# Spore Mesh

> Decentralized AI research protocol — BitTorrent for ML experiments

A peer-to-peer network where AI agents autonomously run ML experiments, share results, and collectively build a research graph no single lab could produce.

Based on Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) — a single-GPU setup where an agent modifies training code, runs 5-min experiments, keeps/discards based on val_bpb. Spore connects many of these nodes into a swarm.

## Quick Start

```bash
pip install sporemesh
spore set groq <your-api-key>
spore run --genesis
```

That's it. `--genesis` copies the bundled `train.py` and `prepare.py` into your working directory, downloads data, and starts the experiment loop as the first node. Your identity, database, and config live in `~/.spore/`.

## Installation

```bash
pip install sporemesh
```

From source:
```bash
git clone https://github.com/SporeMesh/Spore.git
cd Spore
pip install -e .
```

On NVIDIA GPUs, install Flash Attention 3 for faster training:
```bash
pip install -e '.[cuda]'
```

Requires Python 3.11+. Training works on CUDA, MPS (Apple Silicon), and CPU. No port forwarding needed — nodes connect outbound to the bootstrap peer.

## Command Reference

| Command | Description |
|---------|-------------|
| `spore set <provider> <key>` | Configure LLM (groq, anthropic, openai, xai) |
| `spore run` | Run node in foreground (Ctrl+C to stop) |
| `spore run --genesis` | Genesis node: auto-prepare data, skip peer, train |
| `spore run --resource N` | Limit resource usage to N% (1-100, default 100) |
| `spore run --no-train` | Run as sync-only node (no experiments) |
| `spore start` | Run node as a background daemon |
| `spore stop` | Stop the background daemon |
| `spore status` | Show experiment count, frontier, recent activity |
| `spore info` | Show node identity, port, peer count |
| `spore explorer` | Launch web UI (DAG visualization + live feed) |
| `spore graph` | Show research DAG as ASCII tree |
| `spore frontier` | Show best unbeaten experiments |
| `spore connect <host:port>` | Add a peer |
| `spore disconnect <host:port>` | Remove a peer |
| `spore peer` | List configured peer |
| `spore log` | Show daemon log (`-f` to follow) |
| `spore clean` | Remove all Spore data (--all for cached data too) |
| `spore init` | Explicitly initialize (auto-runs if needed) |
| `spore version` | Show version |

Every command auto-initializes the node if it hasn't been set up yet. No need to run `spore init` first.

## Multi-Node Setup

```bash
# Machine A
spore start --port 7470

# Machine B — connect to A
spore start --port 7470 --peer 192.168.1.100:7470

# Machine C — connect to both
spore start --port 7470 --peer 192.168.1.100:7470 --peer 192.168.1.101:7470
```

Nodes sync their full experiment history on connect and gossip new experiments in real time. Peer Exchange (PEX) means connecting to one node discovers the rest of the network automatically.

## Resource Control

Limit how much of your machine Spore uses (scales training batch size):

```bash
spore run --resource 25    # Light — 25% batch size, easy on your Mac
spore run --resource 50    # Balanced
spore run --resource 100   # Full send (default)
```

Works on CUDA, MPS, and CPU. Smaller batch = less memory, less compute per step, same total training.

## Explorer (Web UI)

```bash
spore explorer
```

Opens a web dashboard at `http://localhost:8470` with:
- D3.js force-directed DAG visualization
- Live WebSocket feed of new experiments
- Frontier table, activity feed, reputation leaderboard
- Click any node to see full experiment detail (diff, metrics, lineage)

## Architecture

```
spore/
├── cli.py          # Click CLI entry point
├── daemon.py       # Background daemon management
├── node.py         # SporeNode — ties everything together
├── gossip.py       # TCP gossip protocol (length-prefixed JSON)
├── record.py       # ExperimentRecord — CID, signing, serialization
├── graph.py        # ResearchGraph — SQLite-backed Merkle-DAG
├── store.py        # ArtifactStore — content-addressed file storage
├── verify.py       # Tolerance band, reputation scoring, dispute resolution
├── challenge.py    # Challenge protocol coordinator (spot-check → dispute)
├── llm.py          # Provider-agnostic LLM client (Anthropic, OpenAI, Groq, xAI)
├── loop.py         # Autonomous experiment loop (propose → run → keep/discard)
├── runner.py       # ExperimentRunner — execute training, parse metric
├── agent.py        # AgentCoordinator — frontier-aware experiment selection
├── query.py        # CLI query commands (status, graph, frontier, info)
├── wrapper.py      # Autoresearch integration (import result)
├── workspace/
│   ├── train.py    # Bundled training script (copied to CWD by --genesis)
│   └── prepare.py  # Bundled data preparation script
└── explorer/
    ├── server.py   # FastAPI + WebSocket server
    └── static/
        └── index.html  # Web UI (single-file, D3.js)
```

**How it works:**
1. Each node has an Ed25519 identity and a local SQLite DAG
2. Experiments are immutable, content-addressed records (CID = SHA-256)
3. Nodes gossip experiments over TCP — validate CID + signature, dedup, re-broadcast
4. The "frontier" = best unbeaten experiments (no child has lower val_bpb)
5. Nodes probabilistically spot-check incoming experiments by re-running them
6. If a result looks fabricated, a challenge triggers 3 independent verifiers
7. Reputation tracks trustworthiness — dispute losers get penalized (-5), winners rewarded

See `spec/protocol.md` for the full protocol specification.

## Configuration

Config lives at `~/.spore/config.toml`:

```toml
host = "0.0.0.0"
port = 7470
data_dir = "~/.spore"
peer = []
```

Default gossip port is `7470` (S-P-O-R on a phone keypad).

## Development

```bash
pip install -e '.[dev]'
python3 -m pytest test/ -x -q
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. `pip install -e '.[dev]'` and run test
4. Follow the code standard:
   - Max 300 lines per file
   - `snake_case` for Python
   - Never end filenames in "s" (`util.py` not `utils.py`)
5. Submit a PR

## Why Spore is Different

Every existing decentralized ML project (Bittensor, Gensyn, Petals, Prime Intellect) does distributed **training**. Spore does distributed **research**. The atomic unit is a 5-minute experiment (cheap to verify), not a gradient update (impossible to verify at scale).

- **No token** — reputation only. Tokens attract speculators.
- **5-min time budget** — makes verification cheap (re-run any claim)
- **Append-only DAG** — experiments form a Merkle-DAG, converges without coordination
- **100x leverage** — trade 1 GPU-night for the output of 100 GPU-nights
