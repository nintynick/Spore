"""Reward calculation and bridge between reputation events and token operations.

This module hooks into the existing reputation system and triggers corresponding
token mints, burns, and slashes via the TokenManager.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import token_config as cfg

if TYPE_CHECKING:
    from .token import TokenManager

log = logging.getLogger(__name__)


class RewardEngine:
    """Translates reputation events into token operations.

    Wraps a TokenManager and provides methods that mirror ReputationStore's
    reward/penalty API, so they can be called in parallel from challenge_state.
    """

    def __init__(self, token_manager: TokenManager):
        self.tm = token_manager

    # -------------------------------------------------------------------
    # Publishing
    # -------------------------------------------------------------------

    def on_publish(self, node_id: str) -> bool:
        """Check and enforce staking requirement for publishing.

        Returns True if the node may publish (sufficient stake or genesis epoch).
        """
        if self.tm.in_genesis_epoch:
            return True
        return self.tm.has_sufficient_stake(node_id, cfg.STAKE_PUBLISH)

    # -------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------

    def on_record_verified(self, node_id: str, is_frontier: bool = False):
        """Reward a node whose experiment was verified."""
        self.tm.reward_verified_keep(node_id, is_frontier=is_frontier)
        log.info(
            "Token reward: %s earned %d $xSPORE (verified %s)",
            node_id[:8],
            cfg.REWARD_VERIFIED_FRONTIER if is_frontier else cfg.REWARD_VERIFIED_KEEP,
            "frontier" if is_frontier else "keep",
        )

    def on_verification_performed(self, verifier_id: str):
        """Reward a verifier for performing a spot-check."""
        self.tm.reward_verification_performed(verifier_id)
        log.info(
            "Token reward: %s earned %d $xSPORE (verification performed)",
            verifier_id[:8],
            cfg.REWARD_VERIFICATION_PERFORMED,
        )

    # -------------------------------------------------------------------
    # Disputes
    # -------------------------------------------------------------------

    def on_successful_challenge(self, challenger_id: str):
        """Reward a challenger who exposed a bad claim."""
        self.tm.reward_successful_challenge(challenger_id)
        log.info(
            "Token reward: %s earned %d $xSPORE (successful challenge)",
            challenger_id[:8],
            cfg.REWARD_SUCCESSFUL_CHALLENGE,
        )

    def on_winning_verifier(self, verifier_id: str):
        """Reward a verifier on the correct side of a resolved dispute."""
        self.tm.reward_winning_verifier(verifier_id)

    def on_wrong_dispute_side(self, node_id: str):
        """Penalize being on the wrong side of a dispute."""
        self.tm.penalize_wrong_dispute_side(node_id)
        log.info(
            "Token penalty: %s lost %d $xSPORE + %d $SPORE slashed (wrong dispute side)",
            node_id[:8],
            cfg.PENALTY_WRONG_DISPUTE_SIDE,
            cfg.SLASH_WRONG_DISPUTE,
        )

    def on_rejected_experiment(self, node_id: str):
        """Heavy penalty for a published claim rejected by dispute."""
        self.tm.penalize_rejected_experiment(node_id)
        log.info(
            "Token penalty: %s lost %d $xSPORE + %d $SPORE slashed (rejected experiment)",
            node_id[:8],
            cfg.PENALTY_REJECTED_EXPERIMENT,
            cfg.SLASH_REJECTED_EXPERIMENT,
        )

    # -------------------------------------------------------------------
    # Challenge staking
    # -------------------------------------------------------------------

    def on_challenge_issued(self, challenger_id: str) -> bool:
        """Check and enforce staking requirement for a challenge.

        Returns True if the node may challenge.
        """
        if self.tm.in_genesis_epoch:
            return True
        return self.tm.has_sufficient_stake(challenger_id, cfg.STAKE_CHALLENGE)
