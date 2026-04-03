import os

from brownie import RatingRouter, accounts, network
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


def main(network_type=None):
    load_dotenv()
    mode = _resolve_mode(network_type)
    deployer = _load_deployer(mode)

    chainlink_router = _require_env("CHAINLINK_ROUTER_ADDRESS")
    sub_id = int(_require_env("CHAINLINK_SUBSCRIPTION_ID"))
    don_id_hex = _require_env("CHAINLINK_DON_ID_HEX")

    print(f"Active network: {network.show_active()}")
    print(f"Mode: {mode}")
    print(f"Deployer: {deployer.address}")
    print(f"Chainlink router: {chainlink_router}")
    print(f"Subscription ID: {sub_id}")
    print(f"DON ID: {don_id_hex}")

    router = RatingRouter.deploy(
        chainlink_router,
        don_id_hex,
        sub_id,
        {"from": deployer},
    )

    print(f"Deployment tx: {router.tx.txid}")
    print(f"RatingRouter deployed at: {router.address}")
    print("Add this address as a Consumer in your Chainlink Functions subscription.")
    return router
