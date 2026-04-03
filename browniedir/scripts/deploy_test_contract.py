import os

from brownie import Skaltuchet, accounts, network
from dotenv import load_dotenv


def _resolve_mode(network_type):
    if network_type:
        return network_type.lower()

    active = network.show_active().lower()
    if any(name in active for name in ("mainnet", "sepolia", "goerli", "holesky", "polygon", "arbitrum", "optimism")):
        return "testnet"
    return "dev"


def main(network_type=None):
    mode = _resolve_mode(network_type)
    if mode in ("dev", "development"):
        if len(accounts) == 0:
            raise ValueError(
                "No local unlocked accounts found. Use network_type='testnet' with DEPLOYER_PRIVATE_KEY in .env."
            )
        deployer = accounts[0]
    elif mode in ("testnet", "live"):
        load_dotenv()
        private_key = os.getenv("DEPLOYER_PRIVATE_KEY")
        if not private_key:
            raise ValueError("DEPLOYER_PRIVATE_KEY is not set in .env")
        deployer = accounts.add(private_key)
    else:
        raise ValueError("network_type must be one of: dev, development, testnet, live")

    print(f"Active network: {network.show_active()}")
    print(f"Mode: {mode}")
    print(f"Deployer: {deployer.address}")

    contract = Skaltuchet.deploy(deployer.address, {"from": deployer})

    print(f"Deployment tx: {contract.tx.txid}")
    print(f"Skaltuchet deployed at: {contract.address}")
    print(f"Owner balance: {contract.balanceOf(deployer.address)}")
    print(f"Contract reserve: {contract.balanceOf(contract.address)}")

    return contract
