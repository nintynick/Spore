"""Token configuration and economic constants for the Spore incentive layer.

Two-token design on Base L2:
  $SPORE  — Liquid ERC-20.  Minted via verified work, used for staking & governance.
  $xSPORE — Non-transferable contribution credits.  Earned through work,
            burned to claim $SPORE with a patience-based maturation curve.

Inspired by MineBean (roasting / patience rewards) and SSS (contribution
credits / governance shells).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Supply
# ---------------------------------------------------------------------------
SPORE_MAX_SUPPLY = 100_000_000  # 100 M $SPORE hard cap
SPORE_DECIMALS = 18
XSPORE_DECIMALS = 18

# ---------------------------------------------------------------------------
# Reward schedule  ($xSPORE earned per verified action)
# ---------------------------------------------------------------------------
REWARD_VERIFIED_KEEP = 100          # Verified 'keep' experiment
REWARD_VERIFIED_FRONTIER = 200      # Verified 'keep' that advances the frontier
REWARD_VERIFICATION_PERFORMED = 50  # Performing a spot-check / verification
REWARD_SUCCESSFUL_CHALLENGE = 100   # Exposing a fraudulent claim
REWARD_WINNING_VERIFIER = 25        # Being on the correct side of a dispute

# ---------------------------------------------------------------------------
# Penalty schedule ($xSPORE burned)
# ---------------------------------------------------------------------------
PENALTY_WRONG_DISPUTE_SIDE = 50     # Being on the wrong side of a dispute
PENALTY_REJECTED_EXPERIMENT = 200   # Publishing a claim rejected by dispute

# ---------------------------------------------------------------------------
# Staking requirements ($SPORE)
# ---------------------------------------------------------------------------
STAKE_PUBLISH = 100       # Minimum stake to publish an experiment
STAKE_CHALLENGE = 50      # Minimum stake to issue a challenge

# ---------------------------------------------------------------------------
# Slashing ($SPORE burned from stake)
# ---------------------------------------------------------------------------
SLASH_WRONG_DISPUTE = 50        # Lost challenge / wrong verifier side
SLASH_REJECTED_EXPERIMENT = 500  # Experiment rejected by dispute

# ---------------------------------------------------------------------------
# Maturation curve  (MineBean-inspired "roasting")
#
# $xSPORE → $SPORE conversion rate improves the longer you wait to claim.
# Claim fees are redistributed to all other unclaimed $xSPORE holders.
# ---------------------------------------------------------------------------
MATURATION_TIERS = [
    # (min_age_days, conversion_rate_pct, claim_fee_pct)
    (0,  50, 50),   # Immediate claim: 50% conversion, 50% fee
    (7,  75, 25),   # After 7 days:   75% conversion, 25% fee
    (14, 90, 10),   # After 14 days:  90% conversion, 10% fee
    (30, 100, 0),   # After 30 days:  100% conversion, 0% fee
]

# ---------------------------------------------------------------------------
# Genesis / bootstrap
# ---------------------------------------------------------------------------
GENESIS_EPOCH_EXPERIMENTS = 1000  # First N verified experiments mint $SPORE directly (no stake required)
BOOTSTRAP_ALLOCATION = 10_000_000  # 10 M $SPORE reserved for initial liquidity / bootstrap

# ---------------------------------------------------------------------------
# Chain config (Base L2)
# ---------------------------------------------------------------------------
BASE_CHAIN_ID = 8453
BASE_SEPOLIA_CHAIN_ID = 84532

# Contract addresses (set after deployment)
SPORE_TOKEN_ADDRESS = ""
XSPORE_TOKEN_ADDRESS = ""
STAKE_MANAGER_ADDRESS = ""
