// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

/// @title HyphaToken ($HYPHA)
/// @notice Non-transferable (soulbound) contribution hyphae for the Mycelia
///         network. The branching filaments that prove a cultivator's work.
///         Earned through verified experiments and spore prints (verifications).
///         Burned to harvest $MYCO via the Substrate contract.
///         "The hyphae remember."
/// @dev Transfer blocked: only growth (mint) and withering (burn) allowed.
///      Governance weight proportional to hypha balance.
contract HyphaToken is ERC20, ERC20Burnable, ERC20Permit, ERC20Votes, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");

    error NonTransferable();

    constructor(address admin)
        ERC20("Hypha Unit", "HYPHA")
        ERC20Permit("Hypha Unit")
    {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(MINTER_ROLE, admin);
        _grantRole(BURNER_ROLE, admin);
    }

    /// @notice Extend hyphae to a cultivator. Only callable by MINTER_ROLE.
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }

    /// @notice Wither hyphae (blight). Only callable by BURNER_ROLE.
    function adminBurn(address from, uint256 amount) external onlyRole(BURNER_ROLE) {
        _burn(from, amount);
    }

    // --- Non-transferable: only growth and withering ---

    function _update(address from, address to, uint256 value)
        internal
        override(ERC20, ERC20Votes)
    {
        if (from != address(0) && to != address(0)) revert NonTransferable();
        super._update(from, to, value);
    }

    function nonces(address owner) public view override(ERC20Permit, Nonces) returns (uint256) {
        return super.nonces(owner);
    }
}
