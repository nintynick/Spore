// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

/// @title ContributionToken ($xSPORE)
/// @notice Non-transferable (soulbound) ERC-20 tracking verified contributions
///         to the Spore research network. Earned through verified experiments
///         and verifications. Burned to claim $SPORE via the StakeManager.
/// @dev Transfer restrictions enforced in _update: only mint (from == 0) and
///      burn (to == 0) are allowed. Governance weight is proportional to
///      contribution balance.
contract ContributionToken is ERC20, ERC20Burnable, ERC20Permit, ERC20Votes, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");

    error NonTransferable();

    constructor(address admin)
        ERC20("Spore Contribution", "xSPORE")
        ERC20Permit("Spore Contribution")
    {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(MINTER_ROLE, admin);
        _grantRole(BURNER_ROLE, admin);
    }

    /// @notice Mint $xSPORE to a contributor. Only callable by MINTER_ROLE.
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }

    /// @notice Burn $xSPORE from an account (for slashing). Only callable by BURNER_ROLE.
    function adminBurn(address from, uint256 amount) external onlyRole(BURNER_ROLE) {
        _burn(from, amount);
    }

    // --- Non-transferable enforcement ---

    function _update(address from, address to, uint256 value)
        internal
        override(ERC20, ERC20Votes)
    {
        // Allow only minting (from == 0) and burning (to == 0)
        if (from != address(0) && to != address(0)) revert NonTransferable();
        super._update(from, to, value);
    }

    function nonces(address owner) public view override(ERC20Permit, Nonces) returns (uint256) {
        return super.nonces(owner);
    }
}
