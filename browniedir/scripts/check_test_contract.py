from brownie import Skaltuchet, Wei, accounts, network


def check_buy(token, buyer, buy_value="0.1 ether"):
    value = Wei(buy_value)
    buyer_tokens_before = token.balanceOf(buyer.address)
    reserve_before = token.balanceOf(token.address)

    tx = token.buyTokensFor(buyer.address, {"from": buyer, "value": value})
    tx.wait(1)

    buyer_tokens_after = token.balanceOf(buyer.address)
    reserve_after = token.balanceOf(token.address)

    print(f"Buy tx: {tx.txid}")
    print(f"Buyer tokens before: {buyer_tokens_before}")
    print(f"Buyer tokens after:  {buyer_tokens_after}")
    print(f"Reserve before:      {reserve_before}")
    print(f"Reserve after:       {reserve_after}")
    return tx


def main(contract_address):
    buyer = accounts[1]
    token = Skaltuchet.at(contract_address)

    print(f"Active network: {network.show_active()}")
    print(f"Buyer (accounts[1]): {buyer.address}")
    print(f"Using deployed contract: {token.address}")

    check_buy(token, buyer)