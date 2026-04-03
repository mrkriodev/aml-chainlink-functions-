// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {FunctionsClient} from "@smartcontractkit/contracts/src/v0.8/functions/v1_3_0/FunctionsClient.sol";
import {FunctionsRequest} from "@smartcontractkit/contracts/src/v0.8/functions/v1_0_0/libraries/FunctionsRequest.sol";


contract RatingGateSecure is FunctionsClient {
    using FunctionsRequest for FunctionsRequest.Request;

    bytes32 public immutable donId;
    uint64 public immutable subscriptionId;

    uint256 public constant MIN_RATING = 50;    
    // ===== STORAGE =====
    struct Deposit {
        address user;
        uint256 amount;
    }

    mapping(bytes32 => Deposit) public pendingRequests;
    mapping(address => bool) public validUsers;

    address[] public validUsersList;

    // ===== EVENTS =====
    event RequestSent(bytes32 indexed requestId, address indexed user, uint256 amount);
    event UserAccepted(address indexed user, uint256 rating, uint256 amount);
    event UserRejected(address indexed user, uint256 rating, uint256 refunded);

    constructor(
        address router,
        bytes32 _donId,
        uint64 _subscriptionId
    ) FunctionsClient(router) {
        donId = _donId;
        subscriptionId = _subscriptionId;
    }

    // ===== RECEIVE ETH =====
    receive() external payable {
        require(msg.value > 0, "No ETH");
        _checkUserAddress(msg.sender, msg.value);
    }

    // ===== REQUEST =====
    function _checkUserAddress(address user, uint256 amount) internal {
        FunctionsRequest.Request memory req;

        string memory source = string(
            abi.encodePacked(
                "const user_address = '",
                toAsciiString(user),
                "';",
                "const url = `https://pumpdumpapp.com/api/rate/${user_address}`;",
                "const res = await Functions.makeHttpRequest({url});",
                "if (!res || res.error) throw Error('Request failed');",
                "const rating = Number(res.data.rate);",
                "if (!Number.isFinite(rating)) throw Error('Invalid rate');",
                "return Functions.encodeUint256(rating);"
            )
        );

        req.initializeRequestForInlineJavaScript(source);

        bytes32 requestId = _sendRequest(
            req.encodeCBOR(),
            subscriptionId,
            300000,
            donId
        );

        pendingRequests[requestId] = Deposit(user, amount);

        emit RequestSent(requestId, user, amount);
    }

    // ===== CALLBACK =====
    function _fulfillRequest(
        bytes32 requestId,
        bytes memory response,
        bytes memory err
    ) internal override {
        // ✅ защита: запрос должен существовать
        Deposit memory dep = pendingRequests[requestId];
        require(dep.user != address(0), "Unknown request");

        // удаляем сразу (anti-replay)
        delete pendingRequests[requestId];

        if (err.length > 0) {
            _refund(dep.user, dep.amount);
            return;
        }

        uint256 rating = abi.decode(response, (uint256));

        if (rating > MIN_RATING) {
            // ✅ принимаем
            if (!validUsers[dep.user]) {
                validUsers[dep.user] = true;
                validUsersList.push(dep.user);
            }

            emit UserAccepted(dep.user, rating, dep.amount);
        } else {
            // ❌ возврат
            _refund(dep.user, dep.amount);
            emit UserRejected(dep.user, rating, dep.amount);
        }
    }

    // ===== REFUND =====
    function _refund(address user, uint256 amount) internal {
        (bool ok, ) = user.call{value: amount}("");
        require(ok, "Refund failed");
    }

    // ===== UTILS =====
    function toAsciiString(address x) internal pure returns (string memory) {
        bytes memory s = new bytes(40);
        for (uint i = 0; i < 20; i++) {
            bytes1 b = bytes1(uint8(uint(uint160(x)) / (2**(8*(19 - i)))));
            bytes1 hi = bytes1(uint8(b) / 16);
            bytes1 lo = bytes1(uint8(b) - 16 * uint8(hi));
            s[2*i] = char(hi);
            s[2*i+1] = char(lo);
        }
        return string(abi.encodePacked("0x", s));
    }

    function char(bytes1 b) internal pure returns (bytes1 c) {
        if (uint8(b) < 10) return bytes1(uint8(b) + 48);
        else return bytes1(uint8(b) + 87);
    }
}