// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import "./MycoToken.sol";
import "./HyphaToken.sol";

/// @title Substrate
/// @notice The growing medium of the Mycelia network. Manages inoculation
///         (staking), blight (slashing), fruiting cycles (maturation), and
///         harvest (claiming). Decomposition fees recycle nutrients to patient
///         cultivators.
///         "The substrate provides."
/// @dev Inspired by MineBean's "roasting" patience mechanic and SSS's
///      contribution-credit streaming model.
contract Substrate is AccessControl, ReentrancyGuard {
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    MycoToken public immutable myco;
    HyphaToken public immutable hypha;

    // --- Inoculation ---
    mapping(address => uint256) public inoculated;

    // --- Fruiting cycle ---
    struct FruitingBody {
        uint256 amount;      // $HYPHA earned
        uint256 grownAt;     // block.timestamp when grown
    }

    mapping(address => FruitingBody[]) public fruitingBodies;
    mapping(address => uint256) public totalUnharvested;

    // Decomposition pool for nutrient redistribution
    uint256 public decompositionPool;
    uint256 public totalNetworkUnharvested;

    // Accumulated nutrients per unharvested hypha (scaled by 1e18)
    uint256 public accNutrientsPerHypha;
    mapping(address => uint256) public nutrientDebt;

    // --- Events ---
    event Inoculated(address indexed cultivator, uint256 amount);
    event Extracted(address indexed cultivator, uint256 amount);
    event Blighted(address indexed cultivator, uint256 amount, string reason);
    event HyphaGrown(address indexed cultivator, uint256 amount, string reason);
    event Harvested(address indexed cultivator, uint256 hyphaConsumed, uint256 mycoYielded, uint256 decomposed);
    event NutrientsRecycled(uint256 totalDecomposed);

    // --- Errors ---
    error InsufficientInoculation();
    error NothingToHarvest();
    error InvalidAmount();

    // --- Fruiting tiers ---
    uint256 private constant PREMATURE = 0;
    uint256 private constant YOUNG = 7 days;
    uint256 private constant MATURE = 14 days;
    uint256 private constant FULL_MATURITY = 30 days;

    constructor(address admin, MycoToken _myco, HyphaToken _hypha) {
        myco = _myco;
        hypha = _hypha;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, admin);
    }

    // -----------------------------------------------------------------------
    // Inoculation (staking)
    // -----------------------------------------------------------------------

    /// @notice Inoculate $MYCO into the substrate.
    function inoculate(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        myco.transferFrom(msg.sender, address(this), amount);
        inoculated[msg.sender] += amount;
        emit Inoculated(msg.sender, amount);
    }

    /// @notice Extract $MYCO from the substrate.
    function extract(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        if (inoculated[msg.sender] < amount) revert InsufficientInoculation();
        inoculated[msg.sender] -= amount;
        myco.transfer(msg.sender, amount);
        emit Extracted(msg.sender, amount);
    }

    // -----------------------------------------------------------------------
    // Operator functions (protocol oracle / relayer)
    // -----------------------------------------------------------------------

    /// @notice Record verified contribution — grow hyphae.
    function growHypha(address cultivator, uint256 amount, string calldata reason)
        external
        onlyRole(OPERATOR_ROLE)
    {
        _settleNutrients(cultivator);

        hypha.mint(cultivator, amount);
        fruitingBodies[cultivator].push(FruitingBody({
            amount: amount,
            grownAt: block.timestamp
        }));
        totalUnharvested[cultivator] += amount;
        totalNetworkUnharvested += amount;

        emit HyphaGrown(cultivator, amount, reason);
    }

    /// @notice Blight — slash inoculated $MYCO (composted).
    function blight(address cultivator, uint256 amount, string calldata reason)
        external
        onlyRole(OPERATOR_ROLE)
    {
        uint256 actual = amount > inoculated[cultivator] ? inoculated[cultivator] : amount;
        if (actual == 0) return;
        inoculated[cultivator] -= actual;
        myco.burn(actual);
        emit Blighted(cultivator, actual, reason);
    }

    /// @notice Wither hyphae (penalty).
    function witherHypha(address cultivator, uint256 amount)
        external
        onlyRole(OPERATOR_ROLE)
    {
        _settleNutrients(cultivator);
        uint256 actual = amount > hypha.balanceOf(cultivator) ? hypha.balanceOf(cultivator) : amount;
        if (actual == 0) return;
        hypha.adminBurn(cultivator, actual);

        uint256 reduction = amount > totalUnharvested[cultivator]
            ? totalUnharvested[cultivator]
            : amount;
        totalUnharvested[cultivator] -= reduction;
        totalNetworkUnharvested -= reduction;
    }

    // -----------------------------------------------------------------------
    // Harvesting (fruiting cycle)
    // -----------------------------------------------------------------------

    /// @notice Harvest matured fruiting bodies: $HYPHA -> $MYCO.
    ///         Decomposition fees recycle nutrients to patient cultivators.
    function harvest() external nonReentrant {
        _settleNutrients(msg.sender);

        FruitingBody[] storage bodies = fruitingBodies[msg.sender];
        if (bodies.length == 0) revert NothingToHarvest();

        uint256 totalHypha;
        uint256 totalMyco;
        uint256 totalDecomposed;

        for (uint256 i = 0; i < bodies.length; i++) {
            uint256 age = block.timestamp - bodies[i].grownAt;
            (uint256 rate, uint256 feePct) = _fruitingRate(age);

            uint256 amount = bodies[i].amount;
            uint256 mycoOut = (amount * rate) / 100;
            uint256 decomposed = (amount * feePct) / 100;

            totalHypha += amount;
            totalMyco += mycoOut;
            totalDecomposed += decomposed;
        }

        delete fruitingBodies[msg.sender];
        totalNetworkUnharvested -= totalUnharvested[msg.sender];
        totalUnharvested[msg.sender] = 0;

        hypha.adminBurn(msg.sender, totalHypha);

        if (totalMyco > 0) {
            myco.mint(msg.sender, totalMyco * 1e18);
        }

        if (totalDecomposed > 0 && totalNetworkUnharvested > 0) {
            accNutrientsPerHypha += (totalDecomposed * 1e18) / totalNetworkUnharvested;
            decompositionPool += totalDecomposed;
            emit NutrientsRecycled(totalDecomposed);
        }

        emit Harvested(msg.sender, totalHypha, totalMyco, totalDecomposed);
    }

    /// @notice Count unharvested fruiting bodies.
    function fruitingBodyCount(address cultivator) external view returns (uint256) {
        return fruitingBodies[cultivator].length;
    }

    /// @notice Estimate harvestable $MYCO.
    function estimateHarvest(address cultivator) external view returns (
        uint256 totalMyco,
        uint256 totalDecomposed,
        uint256 totalHypha
    ) {
        FruitingBody[] storage bodies = fruitingBodies[cultivator];
        for (uint256 i = 0; i < bodies.length; i++) {
            uint256 age = block.timestamp - bodies[i].grownAt;
            (uint256 rate, uint256 feePct) = _fruitingRate(age);
            uint256 amount = bodies[i].amount;
            totalMyco += (amount * rate) / 100;
            totalDecomposed += (amount * feePct) / 100;
            totalHypha += amount;
        }
    }

    // -----------------------------------------------------------------------
    // Internal
    // -----------------------------------------------------------------------

    function _fruitingRate(uint256 age) internal pure returns (uint256 rate, uint256 feePct) {
        if (age >= FULL_MATURITY) return (100, 0);   // Full maturity
        if (age >= MATURE)        return (90, 10);    // Mature
        if (age >= YOUNG)         return (75, 25);    // Young
        return (50, 50);                               // Premature
    }

    function _settleNutrients(address cultivator) internal {
        uint256 unharvested = totalUnharvested[cultivator];
        if (unharvested > 0) {
            uint256 owed = (unharvested * accNutrientsPerHypha) / 1e18 - nutrientDebt[cultivator];
            if (owed > 0) {
                hypha.mint(cultivator, owed);
            }
        }
        nutrientDebt[cultivator] = (totalUnharvested[cultivator] * accNutrientsPerHypha) / 1e18;
    }
}
