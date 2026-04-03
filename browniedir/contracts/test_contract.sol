// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract Skaltuchet is ERC20, Ownable {
    uint256 public constant TOKENS_PER_ETH = 1000;
    uint256 public constant INITIAL_SUPPLY = 1000000 * 10**18; // 1 million tokens, considering 18 decimals

    // Event to track token purchases
    event TokensPurchased(address indexed buyer, uint256 amountOfETH, uint256 amountOfTokens);

    constructor(address initialOwner) ERC20("Skaltuchet", "SKT") Ownable(initialOwner) {
        _mint(initialOwner, INITIAL_SUPPLY / 2);       // Mint 500,000 tokens to the deployer
        _mint(address(this), INITIAL_SUPPLY / 2);    // Mint 500,000 tokens to the contract itself
    }

    function buyTokens() public payable {
        _buyTokens(msg.sender);
    }

    function buyTokensFor(address recipient) public payable {
        require(recipient != address(0), "Invalid recipient");
        _buyTokens(recipient);
    }

    function _buyTokens(address recipient) internal {
        require(msg.value > 0, "Send ETH to buy tokens");

        uint256 tokensToBuy = (msg.value * TOKENS_PER_ETH * 10**decimals()) / 1 ether;
        require(balanceOf(address(this)) >= tokensToBuy, "Not enough tokens in the reserve");

        _transfer(address(this), recipient, tokensToBuy);

        // Emit the TokensPurchased event
        emit TokensPurchased(recipient, msg.value, tokensToBuy);
    }
}