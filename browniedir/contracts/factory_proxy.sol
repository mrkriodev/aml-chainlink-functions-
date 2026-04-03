// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./partner_proxy.sol";

contract RateProxyFactory {
    address public router;

    event ProxyCreated(address proxy, address owner);

    constructor(address _router) {
        router = _router;
    }

    function createProxy() external returns (address) {
        ServiceDepositProxy service_proxy = new ServiceDepositProxy(router, msg.sender);

        emit ProxyCreated(address(service_proxy), msg.sender);

        return address(service_proxy);
    }
}