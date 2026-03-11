// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import "../src/MycoToken.sol";
import "../src/HyphaToken.sol";
import "../src/Substrate.sol";

/// @notice Deployment script for the Mycelia fungal intelligence network on Base.
///         Usage: forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast
contract DeployMycelia is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy tokens
        MycoToken myco = new MycoToken(deployer);
        HyphaToken hypha = new HyphaToken(deployer);

        // 2. Deploy Substrate
        Substrate substrate = new Substrate(deployer, myco, hypha);

        // 3. Grant Substrate roles on both tokens
        myco.grantRole(myco.MINTER_ROLE(), address(substrate));
        hypha.grantRole(hypha.MINTER_ROLE(), address(substrate));
        hypha.grantRole(hypha.BURNER_ROLE(), address(substrate));

        // 4. Seed the substrate with initial $MYCO
        myco.mint(deployer, 10_000_000 * 1e18);

        vm.stopBroadcast();

        console.log("MycoToken ($MYCO):   ", address(myco));
        console.log("HyphaToken ($HYPHA): ", address(hypha));
        console.log("Substrate:           ", address(substrate));
        console.log("");
        console.log("Trust the mycelium. The substrate provides.");
    }
}
