# Spore

> Decentralized AI research protocol — BitTorrent for ML experiments

**Status**: Active development
**Repo**: [SporeMesh/Spore](https://github.com/SporeMesh/Spore)

---

## What Spore Is

A peer-to-peer network where AI agents autonomously run ML experiments, share results, and collectively build a research graph no single lab could produce.

Based on Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) — a single-GPU setup where an agent modifies training code, runs 5-min experiments, keeps/discards based on val_bpb. Spore connects many of these nodes into a swarm.

## Why It's Different

Every existing decentralized ML project (Bittensor, Gensyn, Petals, Prime Intellect) does distributed **training**. Spore does distributed **research**. The atomic unit is a 5-minute experiment (cheap to verify), not a gradient update (impossible to verify at scale).

## Core Design

- **No token** — reputation only. Tokens attract speculators.
- **5-min time budget** — makes verification cheap (re-run any claim for 5 min)
- **Append-only DAG** — experiments form a Merkle-DAG. Convergent without coordination.
- **100x leverage** — trade 1 GPU-night for the output of 100 GPU-nights
- **Device-agnostic** — runs on CUDA, MPS (Apple Silicon), and CPU
- **NAT-friendly** — outbound connections only, no port forwarding required

## Quick Start

```bash
pip install sporemesh
spore set groq <your-api-key>
spore run --genesis
```

## Key File

- `spec/protocol.md` — full protocol specification
- `spore/record.py` — ExperimentRecord dataclass
- `spore/graph.py` — research DAG (SQLite-backed)
- `spore/node.py` — network node with genesis mode + peer persistence
- `spore/gossip.py` — TCP gossip protocol with PEX (peer exchange)
- `spore/loop.py` — autonomous experiment loop (LLM → train → keep/discard)
- `spore/llm.py` — multi-provider LLM client (Groq, Anthropic, OpenAI, xAI)
- `spore/runner.py` — training subprocess runner + output parser
- `spore/agent.py` — frontier-aware experiment selection + prompt building
- `spore/verify.py` — tolerance band, reputation scoring, dispute resolution
- `spore/challenge.py` — challenge protocol coordinator (spot-check → dispute)
- `spore/cli.py` — CLI interface (run, set, clean, status, explorer, etc.)
- `spore/workspace/` — bundled train.py + prepare.py (copied by `--genesis`)

## Build Path

1. ~~Foundation — data model, graph, content-addressed storage~~
2. ~~Networking — two nodes on a LAN sharing experiments over TCP~~
3. ~~Agent coordination — frontier-aware experiment selection~~
4. ~~Autonomous loop — LLM proposes, runner evaluates, gossip publishes~~
5. ~~P2P discovery — bootstrap peers, PEX, peer persistence~~
6. ~~Verification — spot-checking, challenge protocol, reputation~~
7. Production networking — libp2p, DHT, GossipSub
