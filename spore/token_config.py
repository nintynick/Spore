"""Mycelia — Fungal Intelligence Network economic constants.

Two-token design on Base L2:
  $MYCO  — Liquid ERC-20 (Mycelium Coin).  The underground network currency.
           Minted via verified work, inoculated (staked) for participation,
           used for governance.
  $HYPHA — Non-transferable contribution credits (Hyphae Units).  The branching
           filaments of the network.  Earned through verified work, burned to
           harvest $MYCO with a patience-based fruiting curve.

Design philosophy:
  MineBean's "roasting" → Fruiting cycle (patience rewards)
  SSS's contribution credits → Hyphae (non-transferable work tokens)
  "Trust the mycelium.  The substrate provides."
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Supply
# ---------------------------------------------------------------------------
MYCO_MAX_SUPPLY = 100_000_000   # 100 M $MYCO hard cap
MYCO_DECIMALS = 18
HYPHA_DECIMALS = 18

# ---------------------------------------------------------------------------
# Reward schedule  ($HYPHA earned per verified action)
# ---------------------------------------------------------------------------
REWARD_VERIFIED_KEEP = 100          # Verified 'keep' experiment — healthy fruiting body
REWARD_VERIFIED_CANOPY = 200        # Verified 'keep' at the canopy (frontier) — rare specimen
REWARD_SPORE_PRINT = 50             # Performing a spore print (verification / spot-check)
REWARD_CONTAMINATION_CATCH = 100    # Catching contamination (exposing fraudulent claim)
REWARD_WINNING_MYCOLOGIST = 25      # Mycologist on correct side of a dispute

# ---------------------------------------------------------------------------
# Penalty schedule ($HYPHA burned)
# ---------------------------------------------------------------------------
PENALTY_BAD_IDENTIFICATION = 50     # Wrong side of a dispute — misidentified the specimen
PENALTY_TOXIC_FRUITING = 200        # Published a claim rejected by dispute — toxic mushroom

# ---------------------------------------------------------------------------
# Inoculation requirements ($MYCO staked)
# ---------------------------------------------------------------------------
INOCULATE_PUBLISH = 100     # Minimum inoculation to fruit an experiment
INOCULATE_CHALLENGE = 50    # Minimum inoculation to call a contamination check

# ---------------------------------------------------------------------------
# Blight ($MYCO burned from inoculation)
# ---------------------------------------------------------------------------
BLIGHT_BAD_ID = 50              # Lost challenge / wrong mycologist side
BLIGHT_TOXIC_FRUITING = 500     # Experiment rejected by dispute — severe contamination

# ---------------------------------------------------------------------------
# Fruiting cycle  (MineBean-inspired patience mechanic)
#
# $HYPHA → $MYCO conversion rate improves the longer you wait to harvest.
# Harvest fees decompose back into the substrate for all other cultivators.
# ---------------------------------------------------------------------------
FRUITING_TIERS = [
    # (min_age_days, conversion_rate_pct, harvest_fee_pct)
    (0,  50, 50),   # Premature harvest: 50% yield, 50% decomposes
    (7,  75, 25),   # Young fruiting:    75% yield, 25% decomposes
    (14, 90, 10),   # Mature fruiting:   90% yield, 10% decomposes
    (30, 100, 0),   # Full maturity:     100% yield, nothing lost
]

# ---------------------------------------------------------------------------
# First Flush (genesis / bootstrap)
# ---------------------------------------------------------------------------
FIRST_FLUSH_EXPERIMENTS = 1000      # First N verified experiments = First Flush
SUBSTRATE_ALLOCATION = 10_000_000   # 10 M $MYCO seeded into the initial substrate

# ---------------------------------------------------------------------------
# Chain config (Base L2)
# ---------------------------------------------------------------------------
BASE_CHAIN_ID = 8453
BASE_SEPOLIA_CHAIN_ID = 84532

# Contract addresses (set after deployment)
MYCO_TOKEN_ADDRESS = ""
HYPHA_TOKEN_ADDRESS = ""
SUBSTRATE_ADDRESS = ""

# ---------------------------------------------------------------------------
# Backward-compatible aliases (used by token.py and rewards.py)
# ---------------------------------------------------------------------------
SPORE_MAX_SUPPLY = MYCO_MAX_SUPPLY
REWARD_VERIFIED_FRONTIER = REWARD_VERIFIED_CANOPY
REWARD_VERIFICATION_PERFORMED = REWARD_SPORE_PRINT
REWARD_SUCCESSFUL_CHALLENGE = REWARD_CONTAMINATION_CATCH
REWARD_WINNING_VERIFIER = REWARD_WINNING_MYCOLOGIST
PENALTY_WRONG_DISPUTE_SIDE = PENALTY_BAD_IDENTIFICATION
PENALTY_REJECTED_EXPERIMENT = PENALTY_TOXIC_FRUITING
STAKE_PUBLISH = INOCULATE_PUBLISH
STAKE_CHALLENGE = INOCULATE_CHALLENGE
SLASH_WRONG_DISPUTE = BLIGHT_BAD_ID
SLASH_REJECTED_EXPERIMENT = BLIGHT_TOXIC_FRUITING
GENESIS_EPOCH_EXPERIMENTS = FIRST_FLUSH_EXPERIMENTS
BOOTSTRAP_ALLOCATION = SUBSTRATE_ALLOCATION
MATURATION_TIERS = FRUITING_TIERS
