// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import "../src/SporeToken.sol";
import "../src/ContributionToken.sol";
import "../src/StakeManager.sol";

/// @notice Deployment script for the Spore token incentive layer on Base.
///         Usage: forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast
contract DeploySpore is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy tokens
        SporeToken spore = new SporeToken(deployer);
        ContributionToken xspore = new ContributionToken(deployer);

        // 2. Deploy StakeManager
        StakeManager manager = new StakeManager(deployer, spore, xspore);

        // 3. Grant StakeManager the MINTER_ROLE on both tokens
        spore.grantRole(spore.MINTER_ROLE(), address(manager));
        xspore.grantRole(xspore.MINTER_ROLE(), address(manager));
        xspore.grantRole(xspore.BURNER_ROLE(), address(manager));

        // 4. Mint bootstrap allocation to deployer
        spore.mint(deployer, 10_000_000 * 1e18);

        vm.stopBroadcast();

        console.log("SporeToken:       ", address(spore));
        console.log("ContributionToken:", address(xspore));
        console.log("StakeManager:     ", address(manager));
    }
}
