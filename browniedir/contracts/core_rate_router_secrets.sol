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

contract RatingRouterWithSecrets is FunctionsClient {
    using FunctionsRequest for FunctionsRequest.Request;

    bytes32 public immutable donId;
    uint64 public immutable subscriptionId;
    address public owner;
    string public apiBaseUrl;

    struct PartnerAuthConfig {
        bool enabled;
        uint8 donHostedSlotId;
        uint64 donHostedVersion;
    }

    struct RequestMeta {
        address consumer;
        address user;
    }

    mapping(bytes32 => RequestMeta) public requests;
    mapping(address => PartnerAuthConfig) public partnerAuth;

    event RatingRequested(bytes32 requestId, address consumer, address user);
    event RatingDelivered(bytes32 requestId, address user, uint256 rating);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event ApiBaseUrlUpdated(string apiBaseUrl);
    event PartnerAuthConfigured(address indexed consumer, bool enabled, uint8 slotId, uint64 version);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    constructor(
        address router,
        bytes32 _donId,
        uint64 _subId
    ) FunctionsClient(router) {
        donId = _donId;
        subscriptionId = _subId;
        owner = msg.sender;
        apiBaseUrl = "https://pumpdumpapp.com/api/rate/";
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Bad owner");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setApiBaseUrl(string calldata newBaseUrl) external onlyOwner {
        require(bytes(newBaseUrl).length > 0, "Empty URL");
        apiBaseUrl = newBaseUrl;
        emit ApiBaseUrlUpdated(newBaseUrl);
    }

    function setPartnerAuthDONHosted(
        address consumer,
        bool enabled,
        uint8 slotId,
        uint64 version
    ) external onlyOwner {
        require(consumer != address(0), "Bad consumer");
        partnerAuth[consumer] = PartnerAuthConfig({
            enabled: enabled,
            donHostedSlotId: slotId,
            donHostedVersion: version
        });
        emit PartnerAuthConfigured(consumer, enabled, slotId, version);
    }

    function requestRating(address user) external returns (bytes32) {
        FunctionsRequest.Request memory req;

        PartnerAuthConfig memory authCfg = partnerAuth[msg.sender];

        string memory source = string(
            abi.encodePacked(
                "const user_address = '",
                toAsciiString(user),
                "';",
                "const url = `",
                apiBaseUrl,
                "${user_address}`;",
                "const headers = {};",
                "if (typeof secrets !== 'undefined' && secrets.AUTHORIZATION) {",
                "  headers['Authorization'] = secrets.AUTHORIZATION;",
                "}",
                "const reqCfg = Object.keys(headers).length > 0 ? {url, headers} : {url};",
                "const res = await Functions.makeHttpRequest(reqCfg);",
                "if (!res || res.error) throw Error('Request failed');",
                "const rating = Number(res.data.rate);",
                "return Functions.encodeUint256(rating);"
            )
        );

        req.initializeRequestForInlineJavaScript(source);
        if (authCfg.enabled) {
            req.addDONHostedSecrets(authCfg.donHostedSlotId, authCfg.donHostedVersion);
        }

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
