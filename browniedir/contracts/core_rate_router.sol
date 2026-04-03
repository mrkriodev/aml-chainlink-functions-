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

contract RatingRouter is FunctionsClient {
    using FunctionsRequest for FunctionsRequest.Request;

    bytes32 public immutable donId;
    uint64 public immutable subscriptionId;

    struct RequestMeta {
        address consumer;
        address user;
    }

    mapping(bytes32 => RequestMeta) public requests;

    event RatingRequested(bytes32 requestId, address consumer, address user);
    event RatingDelivered(bytes32 requestId, address user, uint256 rating);

    constructor(
        address router,
        bytes32 _donId,
        uint64 _subId
    ) FunctionsClient(router) {
        donId = _donId;
        subscriptionId = _subId;
    }

    function requestRating(address user) external returns (bytes32) {
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

        emit RatingRequested(requestId, msg.sender, user);

        return requestId;
    }

    function _fulfillRequest(
        bytes32 requestId,
        bytes memory response,
        bytes memory err
    ) internal override {
        RequestMeta memory meta = requests[requestId];
        require(meta.consumer != address(0), "Bad request");

        delete requests[requestId];

        if (err.length > 0) {
            IRatingConsumer(meta.consumer).handleRating(
                requestId,
                meta.user,
                0
            );
            return;
        }

        uint256 rating = abi.decode(response, (uint256));

        IRatingConsumer(meta.consumer).handleRating(
            requestId,
            meta.user,
            rating
        );

        emit RatingDelivered(requestId, meta.user, rating);
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