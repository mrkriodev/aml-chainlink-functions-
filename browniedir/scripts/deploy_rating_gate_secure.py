import os

from brownie import RatingGateSecure, accounts, network
from dotenv import load_dotenv


DEFAULT_DON_ID_TEXT = "fun-ethereum-sepolia-1"


def _resolve_mode(network_type):
    if network_type:
        return network_type.lower()

    active = network.show_active().lower()
    if any(name in active for name in ("mainnet", "sepolia", "goerli", "holesky", "polygon", "arbitrum", "optimism")):
        return "testnet"
    return "dev"


def _bytes32_from_text(value):
    raw = value.encode("utf-8")
    if len(raw) > 32:
        raise ValueError("CHAINLINK_DON_ID_TEXT must be 32 bytes or less")
    return "0x" + raw.hex().ljust(64, "0")


def _resolve_don_id():
    don_id_hex = os.getenv("CHAINLINK_DON_ID_HEX")
    if don_id_hex:
        if not don_id_hex.startswith("0x") or len(don_id_hex) != 66:
            raise ValueError("CHAINLINK_DON_ID_HEX must be a 32-byte hex string (0x + 64 chars)")
        return don_id_hex

    don_id_text = os.getenv("CHAINLINK_DON_ID_TEXT", DEFAULT_DON_ID_TEXT)
    return _bytes32_from_text(don_id_text)


def _load_deployer(mode):
    if mode in ("dev", "development"):
        if len(accounts) == 0:
            raise ValueError(
                "No local unlocked accounts found. Use network_type='testnet' with DEPLOYER_PRIVATE_KEY in .env."
            )
        return accounts[0]

    if mode in ("testnet", "live"):
        private_key = os.getenv("DEPLOYER_PRIVATE_KEY")
        if not private_key:
            raise ValueError("DEPLOYER_PRIVATE_KEY is not set in .env")
        return accounts.add(private_key)

    raise ValueError("network_type must be one of: dev, development, testnet, live")


def main(network_type=None):
    load_dotenv()
    mode = _resolve_mode(network_type)
    deployer = _load_deployer(mode)

    router = os.getenv("CHAINLINK_ROUTER_ADDRESS")
    if not router:
        raise ValueError("CHAINLINK_ROUTER_ADDRESS is not set in .env")

    sub_id_raw = os.getenv("CHAINLINK_SUBSCRIPTION_ID")
    if not sub_id_raw:
        raise ValueError("CHAINLINK_SUBSCRIPTION_ID is not set in .env")
    subscription_id = int(sub_id_raw)

    don_id = _resolve_don_id()

    print(f"Active network: {network.show_active()}")
    print(f"Mode: {mode}")
    print(f"Deployer: {deployer.address}")
    print(f"Router: {router}")
    print(f"Subscription ID: {subscription_id}")
    print(f"DON ID: {don_id}")

    contract = RatingGateSecure.deploy(
        router,
        don_id,
        subscription_id,
        {"from": deployer},
    )

    print(f"Deployment tx: {contract.tx.txid}")
    print(f"RatingGateSecure deployed at: {contract.address}")
    return contract
