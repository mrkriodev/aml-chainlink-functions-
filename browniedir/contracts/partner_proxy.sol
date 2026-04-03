// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IRatingRouter {
    function requestRating(address user) external returns (bytes32);
}

contract ServiceDepositProxy {
    address public router;
    address public owner;
    bool public initialized;

    uint256 public constant MIN_RATING = 50;

    mapping(address => uint256) public balances;
    mapping(address => uint256) public senderRate;
    mapping(address => bool) public senderAccepted;
    mapping(address => bool) public partnerUsers;

    struct PendingRequest {
        address sender;
        address beneficiary;
        uint256 amount;
    }

    mapping(bytes32 => PendingRequest) public pendingRequests;

    event RatingHandled(bytes32 indexed requestId, address indexed user, uint256 rating, bool accepted);
    event DepositRequested(bytes32 indexed requestId, address indexed sender, address indexed beneficiary, uint256 amount);
    event PartnerUserSet(address indexed user, bool allowed);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event Initialized(address indexed router, address indexed owner);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyInitialized() {
        require(initialized, "Not initialized");
        _;
    }

    constructor() {
        initialized = true;
    }

    function initialize(address _router, address _owner) external {
        require(!initialized, "Already initialized");
        require(_router != address(0), "Bad router");
        require(_owner != address(0), "Bad owner");
        router = _router;
        owner = _owner;
        initialized = true;
        emit Initialized(_router, _owner);
    }

    receive() external payable onlyInitialized {
        revert("Use depositFor(address)");
    }

    function transferOwnership(address newOwner) external onlyInitialized onlyOwner {
        require(newOwner != address(0), "Bad owner");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setPartnerUser(address user, bool allowed) external onlyInitialized onlyOwner {
        require(user != address(0), "Bad user");
        partnerUsers[user] = allowed;
        emit PartnerUserSet(user, allowed);
    }

    function setPartnerUsers(address[] calldata users, bool allowed) external onlyInitialized onlyOwner {
        for (uint256 i = 0; i < users.length; i++) {
            address user = users[i];
            require(user != address(0), "Bad user");
            partnerUsers[user] = allowed;
            emit PartnerUserSet(user, allowed);
        }
    }

    function depositFor(address beneficiary) external payable onlyInitialized returns (bytes32 requestId) {
        require(msg.value > 0, "No ETH");
        require(partnerUsers[beneficiary], "Unknown partner user");

        requestId = IRatingRouter(router).requestRating(msg.sender);
        pendingRequests[requestId] = PendingRequest(msg.sender, beneficiary, msg.value);
        emit DepositRequested(requestId, msg.sender, beneficiary, msg.value);
    }

    function handleRating(
        bytes32 requestId,
        address user,
        uint256 rating
    ) external onlyInitialized {
        require(msg.sender == router, "Only router");

        PendingRequest memory req = pendingRequests[requestId];
        require(req.sender != address(0), "Unknown request");
        require(req.sender == user, "Mismatch");
        delete pendingRequests[requestId];

        senderRate[user] = rating;
        bool accepted = rating > MIN_RATING;
        senderAccepted[user] = accepted;
        emit RatingHandled(requestId, user, rating, accepted);

        if (accepted) {
            balances[req.beneficiary] += req.amount;
        } else {
            (bool ok, ) = req.sender.call{value: req.amount}("");
            require(ok, "Refund failed");
        }
    }

    function getSenderRateState(address user) external view onlyInitialized returns (uint256 rating, bool accepted) {
        rating = senderRate[user];
        accepted = senderAccepted[user];
    }
}