// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {FunctionsClient} from "@smartcontractkit/contracts/src/v0.8/functions/v1_3_0/FunctionsClient.sol";
import {FunctionsRequest} from "@smartcontractkit/contracts/src/v0.8/functions/v1_0_0/libraries/FunctionsRequest.sol";

interface IRatingConsumer {
    function handleRating(
        bytes32 requestId,
        address user,
        uint256 rating
    ) external;
}

contract RatingRouterWithFallback is FunctionsClient {
    using FunctionsRequest for FunctionsRequest.Request;

    bytes32 public immutable donId;
    uint64 public immutable subscriptionId;

    address public signer; // backend signer

    struct RequestMeta {
        address consumer;
        address user;
    }

    mapping(bytes32 => RequestMeta) public requests;

    event FallbackUsed(bytes32 requestId, address user, uint256 rating);

    constructor(
        address router,
        bytes32 _donId,
        uint64 _subId,
        address _signer
    ) FunctionsClient(router) {
        donId = _donId;
        subscriptionId = _subId;
        signer = _signer;
    }

    function requestRating(address user) external returns (bytes32) {
        FunctionsRequest.Request memory req;

        string memory source = string(
            abi.encodePacked(
                "const user = '",
                toAsciiString(user),
                "';",
                "const url = `https://pumpdumpapp.com/api/rate/${user}`;",
                "const res = await Functions.makeHttpRequest({url});",
                "if (!res || res.error) throw Error('Request failed');",
                "const rating = Number(res.data.rate);",
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

        requests[requestId] = RequestMeta(msg.sender, user);

        return requestId;
    }

    // ===== PRIMARY ORACLE =====
    function _fulfillRequest(
        bytes32 requestId,
        bytes memory response,
        bytes memory err
    ) internal override {
        RequestMeta memory meta = requests[requestId];
        require(meta.consumer != address(0), "Bad request");

        delete requests[requestId];

        if (err.length > 0) {
            // ❗ не вызываем consumer → ждём fallback
            return;
        }

        uint256 rating = abi.decode(response, (uint256));

        IRatingConsumer(meta.consumer).handleRating(
            requestId,
            meta.user,
            rating
        );
    }

    // ===== FALLBACK ENTRY =====
    function fulfillFallback(
        bytes32 requestId,
        address user,
        uint256 rating,
        uint256 timestamp,
        bytes calldata signature
    ) external {
        RequestMeta memory meta = requests[requestId];
        require(meta.consumer != address(0), "No request");

        require(meta.user == user, "User mismatch");

        // ⏱ защита от replay
        require(block.timestamp - timestamp < 5 minutes, "Expired");

        // 🔐 проверка подписи
        bytes32 hash = keccak256(
            abi.encode(requestId, user, rating, timestamp)
        );

        address recovered = recover(hash, signature);
        require(recovered == signer, "Bad signature");

        delete requests[requestId];

        IRatingConsumer(meta.consumer).handleRating(
            requestId,
            user,
            rating
        );

        emit FallbackUsed(requestId, user, rating);
    }

    // ===== ECDSA =====
    function recover(bytes32 hash, bytes memory sig)
        internal
        pure
        returns (address)
    {
        bytes32 ethHash = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", hash)
        );

        (bytes32 r, bytes32 s, uint8 v) = split(sig);
        return ecrecover(ethHash, v, r, s);
    }

    function split(bytes memory sig)
        internal
        pure
        returns (bytes32 r, bytes32 s, uint8 v)
    {
        require(sig.length == 65, "bad sig");

        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
    }

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