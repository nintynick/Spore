// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import "./SporeToken.sol";
import "./ContributionToken.sol";

/// @title StakeManager
/// @notice Manages staking, slashing, maturation, and reward distribution for
///         the Spore protocol. Nodes stake $SPORE to publish experiments;
///         verified work earns $xSPORE which matures into claimable $SPORE.
/// @dev Inspired by MineBean's "roasting" patience mechanic and SSS's
///      contribution-credit streaming model.
contract StakeManager is AccessControl, ReentrancyGuard {
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    SporeToken public immutable spore;
    ContributionToken public immutable xspore;

    // --- Staking ---
    mapping(address => uint256) public staked;

    // --- Maturation (MineBean-inspired patience rewards) ---
    struct PendingReward {
        uint256 amount;      // $xSPORE earned
        uint256 earnedAt;    // block.timestamp when earned
    }

    mapping(address => PendingReward[]) public pendingRewards;
    mapping(address => uint256) public totalPendingXSpore;

    // Global pool of claim fees for redistribution
    uint256 public claimFeePool;
    uint256 public totalUnclaimed; // sum of all unclaimed $xSPORE across users

    // Accumulated fee per unclaimed token (scaled by 1e18)
    uint256 public accFeePerUnclaimed;
    mapping(address => uint256) public feeDebt;

    // --- Events ---
    event Staked(address indexed node, uint256 amount);
    event Unstaked(address indexed node, uint256 amount);
    event Slashed(address indexed node, uint256 amount, string reason);
    event RewardEarned(address indexed node, uint256 xsporeAmount, string reason);
    event RewardClaimed(address indexed node, uint256 xsporeBurned, uint256 sporeMinted, uint256 fee);
    event FeeRedistributed(uint256 totalFee);

    // --- Errors ---
    error InsufficientStake();
    error NothingToClaim();
    error InvalidAmount();

    // --- Maturation tiers ---
    uint256 private constant TIER_0_DAYS = 0;
    uint256 private constant TIER_1_DAYS = 7 days;
    uint256 private constant TIER_2_DAYS = 14 days;
    uint256 private constant TIER_3_DAYS = 30 days;

    constructor(address admin, SporeToken _spore, ContributionToken _xspore) {
        spore = _spore;
        xspore = _xspore;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, admin);
    }

    // -----------------------------------------------------------------------
    // Staking
    // -----------------------------------------------------------------------

    /// @notice Stake $SPORE to participate in the protocol.
    function stake(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        spore.transferFrom(msg.sender, address(this), amount);
        staked[msg.sender] += amount;
        emit Staked(msg.sender, amount);
    }

    /// @notice Unstake $SPORE (only excess above minimum publish stake).
    function unstake(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        if (staked[msg.sender] < amount) revert InsufficientStake();
        staked[msg.sender] -= amount;
        spore.transfer(msg.sender, amount);
        emit Unstaked(msg.sender, amount);
    }

    // -----------------------------------------------------------------------
    // Operator functions (called by protocol oracle / relayer)
    // -----------------------------------------------------------------------

    /// @notice Record a verified contribution and mint $xSPORE.
    function recordReward(address node, uint256 xsporeAmount, string calldata reason)
        external
        onlyRole(OPERATOR_ROLE)
    {
        // Settle pending fee share before changing unclaimed balance
        _settleFees(node);

        xspore.mint(node, xsporeAmount);
        pendingRewards[node].push(PendingReward({
            amount: xsporeAmount,
            earnedAt: block.timestamp
        }));
        totalPendingXSpore[node] += xsporeAmount;
        totalUnclaimed += xsporeAmount;

        emit RewardEarned(node, xsporeAmount, reason);
    }

    /// @notice Slash a node's staked $SPORE (burn it).
    function slash(address node, uint256 amount, string calldata reason)
        external
        onlyRole(OPERATOR_ROLE)
    {
        uint256 actual = amount > staked[node] ? staked[node] : amount;
        if (actual == 0) return;
        staked[node] -= actual;
        spore.burn(actual);
        emit Slashed(node, actual, reason);
    }

    /// @notice Burn $xSPORE as a penalty.
    function penalizeContribution(address node, uint256 amount)
        external
        onlyRole(OPERATOR_ROLE)
    {
        _settleFees(node);
        uint256 actual = amount > xspore.balanceOf(node) ? xspore.balanceOf(node) : amount;
        if (actual == 0) return;
        xspore.adminBurn(node, actual);

        // Update unclaimed tracking
        uint256 pendingReduction = amount > totalPendingXSpore[node]
            ? totalPendingXSpore[node]
            : amount;
        totalPendingXSpore[node] -= pendingReduction;
        totalUnclaimed -= pendingReduction;
    }

    // -----------------------------------------------------------------------
    // Claiming (maturation / "roasting")
    // -----------------------------------------------------------------------

    /// @notice Claim matured $xSPORE → $SPORE. Claim fee depends on age.
    ///         Fees are redistributed to all unclaimed $xSPORE holders.
    function claim() external nonReentrant {
        _settleFees(msg.sender);

        PendingReward[] storage rewards = pendingRewards[msg.sender];
        if (rewards.length == 0) revert NothingToClaim();

        uint256 totalXBurned;
        uint256 totalSporeMinted;
        uint256 totalFee;

        for (uint256 i = 0; i < rewards.length; i++) {
            uint256 age = block.timestamp - rewards[i].earnedAt;
            (uint256 rate, uint256 feePct) = _maturationRate(age);

            uint256 xAmount = rewards[i].amount;
            uint256 sporeOut = (xAmount * rate) / 100;
            uint256 fee = (xAmount * feePct) / 100;

            totalXBurned += xAmount;
            totalSporeMinted += sporeOut;
            totalFee += fee;
        }

        // Clear all pending rewards
        delete pendingRewards[msg.sender];
        totalUnclaimed -= totalPendingXSpore[msg.sender];
        totalPendingXSpore[msg.sender] = 0;

        // Burn $xSPORE
        xspore.adminBurn(msg.sender, totalXBurned);

        // Mint $SPORE to claimer
        if (totalSporeMinted > 0) {
            spore.mint(msg.sender, totalSporeMinted * 1e18);
        }

        // Redistribute claim fees to remaining unclaimed holders
        if (totalFee > 0 && totalUnclaimed > 0) {
            accFeePerUnclaimed += (totalFee * 1e18) / totalUnclaimed;
            claimFeePool += totalFee;
            emit FeeRedistributed(totalFee);
        }

        emit RewardClaimed(msg.sender, totalXBurned, totalSporeMinted, totalFee);
    }

    /// @notice View pending rewards and their maturation status.
    function pendingRewardCount(address node) external view returns (uint256) {
        return pendingRewards[node].length;
    }

    /// @notice Estimate total $SPORE claimable now for a node.
    function estimateClaim(address node) external view returns (
        uint256 totalSpore,
        uint256 totalFee,
        uint256 totalXBurned
    ) {
        PendingReward[] storage rewards = pendingRewards[node];
        for (uint256 i = 0; i < rewards.length; i++) {
            uint256 age = block.timestamp - rewards[i].earnedAt;
            (uint256 rate, uint256 feePct) = _maturationRate(age);
            uint256 xAmount = rewards[i].amount;
            totalSpore += (xAmount * rate) / 100;
            totalFee += (xAmount * feePct) / 100;
            totalXBurned += xAmount;
        }
    }

    // -----------------------------------------------------------------------
    // Internal
    // -----------------------------------------------------------------------

    function _maturationRate(uint256 age) internal pure returns (uint256 rate, uint256 feePct) {
        if (age >= TIER_3_DAYS) return (100, 0);
        if (age >= TIER_2_DAYS) return (90, 10);
        if (age >= TIER_1_DAYS) return (75, 25);
        return (50, 50);
    }

    function _settleFees(address node) internal {
        uint256 pending = totalPendingXSpore[node];
        if (pending > 0) {
            uint256 owed = (pending * accFeePerUnclaimed) / 1e18 - feeDebt[node];
            if (owed > 0) {
                // Mint bonus $xSPORE from fee redistribution
                xspore.mint(node, owed);
            }
        }
        feeDebt[node] = (totalPendingXSpore[node] * accFeePerUnclaimed) / 1e18;
    }
}
