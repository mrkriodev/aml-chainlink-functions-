import os

from brownie import RateProxyFactory, accounts, network
from dotenv import load_dotenv


def _require_env(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not set in .env")
    return value


def _resolve_mode(network_type):
    if network_type:
        return network_type.lower()

    active = network.show_active().lower()
    if any(name in active for name in ("mainnet", "sepolia", "goerli", "holesky", "polygon", "arbitrum", "optimism")):
        return "testnet"
    return "dev"


def _load_deployer(mode):
    if mode in ("dev", "development"):
        if len(accounts) == 0:
            raise ValueError(
                "No local unlocked accounts found. Use network_type='testnet' with DEPLOYER_PRIVATE_KEY in .env."
            )
        return accounts[0]

    if mode in ("testnet", "live"):
        private_key = _require_env("DEPLOYER_PRIVATE_KEY")
        return accounts.add(private_key)

    raise ValueError("network_type must be one of: dev, development, testnet, live")


def main(router_address=None, network_type=None):
    load_dotenv()
    mode = _resolve_mode(network_type)
    deployer = _load_deployer(mode)

    if not router_address:
        router_address = _require_env("CORE_RATE_ROUTER_ADDRESS")

    print(f"Active network: {network.show_active()}")
    print(f"Mode: {mode}")
    print(f"Deployer: {deployer.address}")
    print(f"Core router: {router_address}")

    factory = RateProxyFactory.deploy(router_address, {"from": deployer})
    print(f"Deployment tx: {factory.tx.txid}")
    print(f"RateProxyFactory deployed at: {factory.address}")
    return factory
