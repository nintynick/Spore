# Mycelia — Fungal Intelligence Network

> *Trust the mycelium. The substrate provides.*

## Overview

Mycelia is the economic incentive layer for the Spore decentralized ML
research network, deployed on **Base L2**. It uses a two-token fungal
economy to coordinate contributions through a system modeled on real
mycorrhizal networks — where underground fungal networks trade nutrients
for mutual benefit.

| Concept | Biological Analog | Crypto Mechanic |
|---------|-------------------|-----------------|
| $MYCO | Mycelium (underground network) | Liquid ERC-20 |
| $HYPHA | Hyphae (branching filaments) | Non-transferable contribution credits |
| Inoculating | Planting spawn in substrate | Staking |
| Harvesting | Picking mushrooms | Claiming rewards |
| Fruiting cycle | Mushroom growth time | Maturation curve |
| Blight | Fungal disease | Slashing |
| Decomposition | Nutrient recycling | Fee redistribution |
| First Flush | First mushroom harvest | Genesis epoch |
| Canopy | Forest top | Leaderboard / frontier |

Design inspired by MineBean (patience-based "roasting") and the
Semi-Sentients Society (contribution credits with governance streaming).

## Tokens

### $MYCO — Mycelium Coin (Liquid)

| Property | Value |
|----------|-------|
| Standard | ERC-20 + Burnable + Permit (EIP-2612) + Votes (ERC-5805) |
| Chain | Base (chain ID 8453) |
| Max Supply | 100,000,000 |
| Decimals | 18 |
| Minting | Protocol-controlled via Substrate contract |
| Transfer | Unrestricted |

**Uses:** Inoculate (stake) to participate, governance voting, DEX trading.

### $HYPHA — Hypha Units (Soulbound)

| Property | Value |
|----------|-------|
| Standard | Non-transferable ERC-20 (soulbound) + Votes |
| Chain | Base |
| Supply | Uncapped (earned through verified work) |
| Transfer | **Blocked** — only growth and withering |

**Uses:** Tracks verified contributions; burned to harvest $MYCO; governance
weight proportional to contribution.

## Reward Schedule

| Event | $HYPHA Grown | Biological Analog |
|-------|-------------|-------------------|
| Verified `keep` experiment | 100 | Healthy fruiting body |
| Verified canopy experiment | 200 | Rare canopy specimen |
| Spore print (verification) | 50 | Mycologist confirmed species |
| Contamination catch | 100 | Caught toxic imposter |
| Winning mycologist | 25 | Correct identification |

## Blight Schedule

| Event | $HYPHA Withered | $MYCO Blighted |
|-------|----------------|----------------|
| Bad identification | 50 | 50 |
| Toxic fruiting (rejected) | 200 | 500 |

## Inoculation Requirements

| Action | $MYCO Required |
|--------|---------------|
| Fruit an experiment (publish) | 100 minimum inoculation |
| Contamination check (challenge) | 50 minimum inoculation |

## Fruiting Cycle (Maturation)

The longer you let your hyphae fruit, the richer the harvest. Premature
harvesting decomposes nutrients back into the substrate for patient cultivators.

| Fruiting Age | Harvest Yield | Decomposition |
|-------------|---------------|---------------|
| Premature (0 days) | 50% | 50% decomposes |
| Young (7 days) | 75% | 25% decomposes |
| Mature (14 days) | 90% | 10% decomposes |
| Full maturity (30 days) | 100% | Nothing lost |

**Decomposition = Nature's recycling.** When an impatient cultivator harvests
early, the decomposed nutrients flow proportionally to all other cultivators
still patiently growing their hyphae.

## First Flush (Genesis)

The first **1,000 verified experiments** constitute the First Flush:
- No inoculation required to fruit or challenge
- Verified experiments grow $MYCO directly (+ $HYPHA)
- Bootstraps the ecosystem without requiring pre-existing $MYCO

**Substrate seeding:** 10,000,000 $MYCO (10% of max supply) seeded by
deployer for initial DEX liquidity.

## Smart Contracts (Foundry, Base L2)

| Contract | Purpose |
|----------|---------|
| `MycoToken.sol` | ERC-20 $MYCO with AccessControl + Permit + Votes |
| `HyphaToken.sol` | Soulbound $HYPHA with admin burn |
| `Substrate.sol` | Inoculation, blight, fruiting, harvesting, decomposition |

Deploy: `forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast`

## CLI Commands

```
spore fungus balance      Show mycelium balances
spore fungus inoculate    Inoculate $MYCO into the substrate
spore fungus extract      Extract $MYCO from the substrate
spore fungus harvest      Harvest matured fruiting bodies
spore fungus canopy       View the canopy (top cultivators)
spore fungus substrate    Global substrate health stats
spore fungus log          Recent mycelium activity
```

## API Endpoints

```
GET /api/token/stats              Global substrate statistics
GET /api/token/leaderboard        Canopy — top cultivators by $HYPHA
GET /api/node/{id}/token          Cultivator token summary
GET /api/node/{id}/token/history  Cultivator mycelium event history
```

## Economic Properties

- **Deflationary:** Blight composts $MYCO permanently
- **Inflationary supply:** $HYPHA grows uncapped through useful work
- **Hard cap:** $MYCO maxes at 100M
- **Patience premium:** Fruiting cycle rewards long-term cultivation
- **Sybil cost:** Inoculation + compute cost of running experiments
- **Quality signal:** Only verified experiments grow hyphae; toxic fruitings get blighted
- **Nutrient cycling:** Decomposed harvest fees feed the patient
