# Spore Token Incentive Layer — Specification

## Overview

The Spore incentive layer adds an ERC-20 token economy on **Base L2** to
coordinate contributions to the decentralized ML research network.  The design
draws from two production models:

| Concept | Inspiration |
|---------|-------------|
| Patience-based maturation ("roasting") | MineBean ($BEAN on Base) |
| Non-transferable contribution credits  | Semi-Sentients Society ($cSSS) |
| Quality-weighted rewards               | SSS corvée system |
| Staking-as-commitment                  | Both |

## Tokens

### $SPORE (Liquid ERC-20)

| Property | Value |
|----------|-------|
| Standard | ERC-20 + Burnable + Permit (EIP-2612) + Votes (ERC-5805) |
| Chain    | Base (chain ID 8453) |
| Max Supply | 100,000,000 |
| Decimals | 18 |
| Minting  | Protocol-controlled via `MINTER_ROLE` (StakeManager contract) |
| Transfer | Unrestricted |

**Uses:**
- Stake to publish experiments (skin in the game)
- Governance voting weight
- Trading on DEXes

### $xSPORE (Contribution Credits)

| Property | Value |
|----------|-------|
| Standard | Non-transferable ERC-20 (soulbound) + Votes |
| Chain    | Base |
| Supply   | Uncapped (inflationary, earned through work) |
| Transfer | **Blocked** — only mint and burn |

**Uses:**
- Tracks verified contributions to the research network
- Burned to claim $SPORE (with maturation multiplier)
- Governance weight proportional to contributions

## Reward Schedule

| Event | $xSPORE Earned |
|-------|---------------|
| Verified `keep` experiment | 100 |
| Verified frontier `keep`   | 200 |
| Verification performed     | 50  |
| Successful challenge       | 100 |
| Winning verifier           | 25  |

## Penalty Schedule

| Event | $xSPORE Burned | $SPORE Slashed |
|-------|---------------|----------------|
| Wrong dispute side | 50 | 50 |
| Rejected experiment | 200 | 500 |

## Staking

| Requirement | $SPORE |
|-------------|--------|
| Publish experiment | 100 (minimum stake) |
| Issue challenge    | 50 (minimum stake) |

Staked $SPORE is locked in the StakeManager contract.  Slashing burns tokens
permanently (deflationary pressure).

## Maturation Curve (Claiming)

Inspired by MineBean's "roasting" mechanic.  When a node earns $xSPORE, the
tokens enter a maturation period.  The longer you wait to claim, the better
the $xSPORE → $SPORE conversion rate:

| Wait Time | Conversion Rate | Claim Fee |
|-----------|----------------|-----------|
| Immediate | 50% | 50% |
| 7 days    | 75% | 25% |
| 14 days   | 90% | 10% |
| 30 days   | 100% | 0%  |

**Fee redistribution:**  Claim fees are redistributed proportionally to all
other nodes still holding unclaimed $xSPORE.  This creates a "last to claim
wins more" dynamic — patient contributors earn passive income from impatient
claimers.

## Genesis Epoch

The first **1,000 verified experiments** constitute the genesis epoch:
- No staking requirement to publish or challenge
- Verified experiments mint $SPORE directly (in addition to $xSPORE)
- Bootstraps initial token distribution without requiring pre-existing $SPORE

After genesis, staking is enforced and $SPORE can only be obtained by claiming
matured $xSPORE or trading.

**Bootstrap allocation:** 10,000,000 $SPORE (10% of max supply) minted to the
deployer for initial DEX liquidity.

## Smart Contracts

Three contracts deployed on Base:

1. **SporeToken.sol** — ERC-20 with AccessControl, Permit, Votes, Burnable
2. **ContributionToken.sol** — Non-transferable ERC-20 with admin burn
3. **StakeManager.sol** — Staking, slashing, maturation, claiming, fee redistribution

Deployment uses Foundry (`forge script`) targeting Base Sepolia (testnet) then
Base mainnet.

## Integration with Spore Protocol

The token layer integrates at these points:

| Spore Component | Integration |
|-----------------|-------------|
| `reputation.py` | Token rewards parallel reputation score changes |
| `challenge_state.py` | Dispute resolution triggers token slashing |
| `node.py` | TokenManager + RewardEngine initialized with node |
| `cli.py` | `spore token` subcommands (balance, stake, claim, leaderboard) |
| `explorer/server.py` | REST API endpoints for token data |

The local token ledger (SQLite) mirrors on-chain state for development and
offline operation.  On-chain settlement via Base L2 is opt-in.

## Economic Properties

- **Deflationary pressure:** Slashing burns $SPORE permanently
- **Inflationary supply:** $xSPORE is uncapped, earned through useful work
- **Hard cap:** $SPORE capped at 100M
- **Patience reward:** Maturation curve incentivizes long-term holding
- **Sybil cost:** Staking + compute cost of running experiments
- **Quality signal:** Only verified experiments earn rewards; rejected ones are heavily penalized
