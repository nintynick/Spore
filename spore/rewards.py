"""Fungal Reward Engine — translates reputation events into mycelium operations.

Bridges the Spore reputation system with the Mycelia token economy.
Each verified contribution extends the mycelium; each fraud is blight.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import token_config as cfg

if TYPE_CHECKING:
    from .token import MyceliumLedger

log = logging.getLogger(__name__)


class FungalRewardEngine:
    """Translates reputation events into mycelium economics.

    Wraps a MyceliumLedger and mirrors the ReputationStore API
    so it can be called in parallel from challenge_state.
    """

    def __init__(self, ledger: MyceliumLedger):
        self.ledger = ledger

    # -------------------------------------------------------------------
    # Fruiting (publishing)
    # -------------------------------------------------------------------

    def on_publish(self, node_id: str) -> bool:
        """Check inoculation requirement for fruiting (publishing).

        Returns True if the cultivator may fruit (sufficient inoculation
        or still in First Flush).
        """
        if self.ledger.in_first_flush:
            return True
        return self.ledger.has_sufficient_inoculation(node_id, cfg.INOCULATE_PUBLISH)

    # -------------------------------------------------------------------
    # Spore printing (verification)
    # -------------------------------------------------------------------

    def on_record_verified(self, node_id: str, is_frontier: bool = False):
        """Reward a cultivator whose experiment was verified — healthy fruiting body."""
        self.ledger.reward_verified_keep(node_id, is_frontier=is_frontier)
        amount = cfg.REWARD_VERIFIED_CANOPY if is_frontier else cfg.REWARD_VERIFIED_KEEP
        log.info(
            "Mycelium reward: %s grew %d $HYPHA (%s)",
            node_id[:8], amount,
            "canopy specimen" if is_frontier else "healthy fruiting",
        )

    def on_verification_performed(self, verifier_id: str):
        """Reward a mycologist for performing a spore print."""
        self.ledger.reward_verification_performed(verifier_id)
        log.info(
            "Mycelium reward: %s grew %d $HYPHA (spore print)",
            verifier_id[:8], cfg.REWARD_SPORE_PRINT,
        )

    # -------------------------------------------------------------------
    # Contamination (disputes)
    # -------------------------------------------------------------------

    def on_successful_challenge(self, challenger_id: str):
        """Reward for catching contamination."""
        self.ledger.reward_successful_challenge(challenger_id)
        log.info(
            "Mycelium reward: %s grew %d $HYPHA (contamination catch)",
            challenger_id[:8], cfg.REWARD_CONTAMINATION_CATCH,
        )

    def on_winning_verifier(self, verifier_id: str):
        """Reward a mycologist on the correct side of a dispute."""
        self.ledger.reward_winning_verifier(verifier_id)

    def on_wrong_dispute_side(self, node_id: str):
        """Bad identification — blight + hypha withering."""
        self.ledger.penalize_wrong_dispute_side(node_id)
        log.info(
            "Blight: %s lost %d $HYPHA + %d $MYCO (bad identification)",
            node_id[:8], cfg.PENALTY_BAD_IDENTIFICATION, cfg.BLIGHT_BAD_ID,
        )

    def on_rejected_experiment(self, node_id: str):
        """Toxic fruiting — severe blight for publishing poison."""
        self.ledger.penalize_rejected_experiment(node_id)
        log.info(
            "Toxic blight: %s lost %d $HYPHA + %d $MYCO (toxic fruiting)",
            node_id[:8], cfg.PENALTY_TOXIC_FRUITING, cfg.BLIGHT_TOXIC_FRUITING,
        )

    # -------------------------------------------------------------------
    # Contamination checks (challenges)
    # -------------------------------------------------------------------

    def on_challenge_issued(self, challenger_id: str) -> bool:
        """Check inoculation for a contamination check (challenge).

        Returns True if the cultivator may challenge.
        """
        if self.ledger.in_first_flush:
            return True
        return self.ledger.has_sufficient_inoculation(challenger_id, cfg.INOCULATE_CHALLENGE)


# Backward-compatible alias
RewardEngine = FungalRewardEngine
