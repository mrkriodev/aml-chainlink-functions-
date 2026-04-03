// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "./partner_proxy.sol";

contract RateProxyFactory {
    using Clones for address;

    address public router;
    address public immutable implementation;

    event ProxyCreated(address proxy, address owner);
    event ImplementationDeployed(address implementation);

    constructor(address _router) {
        require(_router != address(0), "Bad router");
        router = _router;
        implementation = address(new ServiceDepositProxy());
        emit ImplementationDeployed(implementation);
    }

    function createProxy() external returns (address) {
        address proxy = implementation.clone();
        ServiceDepositProxy(payable(proxy)).initialize(router, msg.sender);
        emit ProxyCreated(proxy, msg.sender);
        return proxy;
    }
}