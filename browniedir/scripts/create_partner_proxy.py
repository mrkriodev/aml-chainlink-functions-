import os

from brownie import RateProxyFactory, ServiceDepositProxy, accounts, network
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


def _load_actor(mode):
    if mode in ("dev", "development"):
        if len(accounts) == 0:
            raise ValueError(
                "No local unlocked accounts found. Use network_type='testnet' with partner private key in .env."
            )
        return accounts[0]

    if mode in ("testnet", "live"):
        partner_key = os.getenv("MY_ADR_WORK_ONE_PRIVE_KEY") or os.getenv("MY_ADR_WORK_ONE_PRIV_KEY")
        if not partner_key:
            raise ValueError("MY_ADR_WORK_ONE_PRIVE_KEY (or MY_ADR_WORK_ONE_PRIV_KEY) is not set in .env")
        return accounts.add(partner_key)

    raise ValueError("network_type must be one of: dev, development, testnet, live")


def _parse_users(users_csv):
    users = []
    for item in users_csv.split(","):
        addr = item.strip()
        if addr:
            users.append(addr)
    return users


def main(factory_address=None, network_type=None):
    load_dotenv()
    mode = _resolve_mode(network_type)
    actor = _load_actor(mode)

    if not factory_address:
        factory_address = _require_env("RATE_PROXY_FACTORY_ADDRESS")

    factory = RateProxyFactory.at(factory_address)
    tx = factory.createProxy({"from": actor})
    tx.wait(1)

    proxy_created = tx.events["ProxyCreated"]
    if isinstance(proxy_created, list):
        proxy_addr = proxy_created[-1]["proxy"]
    else:
        proxy_addr = proxy_created["proxy"]

    print(f"Active network: {network.show_active()}")
    print(f"Creator: {actor.address}")
    print(f"Factory: {factory.address}")
    print(f"Create tx: {tx.txid}")
    print(f"Partner proxy created at: {proxy_addr}")

    users_csv = os.getenv("PARTNER_USERS_CSV", "")
    users = _parse_users(users_csv)
    if users:
        proxy = ServiceDepositProxy.at(proxy_addr)
        setup_tx = proxy.setPartnerUsers(users, True, {"from": actor})
        setup_tx.wait(1)
        print(f"Partner users configured: {len(users)}")
        print(f"Setup tx: {setup_tx.txid}")
    else:
        print("PARTNER_USERS_CSV is empty; no partner user addresses configured.")

    return proxy_addr
