import os

from brownie import RatingRouterWithSecrets, accounts, network
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


def _load_owner(mode):
    if mode in ("dev", "development"):
        if len(accounts) == 0:
            raise ValueError("No local unlocked accounts found")
        return accounts[0]
    if mode in ("testnet", "live"):
        return accounts.add(_require_env("DEPLOYER_PRIVATE_KEY"))
    raise ValueError("network_type must be one of: dev, development, testnet, live")


def main(
    router_address=None,
    partner_proxy_address=None,
    enabled="true",
    slot_id="0",
    version="0",
    network_type=None,
):
    load_dotenv()
    mode = _resolve_mode(network_type)
    owner = _load_owner(mode)

    if not router_address:
        router_address = _require_env("CORE_RATE_ROUTER_ADDRESS")
    if not partner_proxy_address:
        partner_proxy_address = _require_env("PARTNER_PROXY_ADDRESS")

    enabled_flag = enabled.lower() in ("1", "true", "yes", "on")
    slot_id = int(slot_id)
    version = int(version)

    router = RatingRouterWithSecrets.at(router_address)
    tx = router.setPartnerAuthDONHosted(
        partner_proxy_address,
        enabled_flag,
        slot_id,
        version,
        {"from": owner},
    )
    tx.wait(1)

    cfg = router.partnerAuth(partner_proxy_address)
    print(f"Active network: {network.show_active()}")
    print(f"Router: {router.address}")
    print(f"Partner proxy (caller): {partner_proxy_address}")
    print(f"Config tx: {tx.txid}")
    print(f"enabled: {cfg[0]}, slotId: {cfg[1]}, version: {cfg[2]}")
