import os
import time

from brownie import ServiceDepositProxy, Wei, accounts, network
from dotenv import load_dotenv


def _require_env(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not set in .env")
    return value


def _parse_users(users_csv):
    users = []
    for item in users_csv.split(","):
        addr = item.strip()
        if addr:
            users.append(addr)
    return users


def _print_user_state(proxy, user):
    rating, accepted = proxy.getSenderRateState(user)
    credited = proxy.balances(user)
    print(f"user: {user}")
    print(f"  senderRate: {rating}")
    print(f"  accepted:   {accepted}")
    print(f"  credited:   {credited}")


def _extract_request_id(tx):
    if "DepositRequested" in tx.events:
        event = tx.events["DepositRequested"]
        if isinstance(event, list):
            return event[-1]["requestId"]
        return event["requestId"]

    if "RequestSent" in tx.events:
        event = tx.events["RequestSent"]
        if isinstance(event, list):
            event = event[-1]
        if "requestId" in event:
            return event["requestId"]
        if "id" in event:
            return event["id"]

    return None


def _wait_for_fulfillment(proxy, request_id, timeout_sec, poll_sec):
    started = time.time()
    while (time.time() - started) < timeout_sec:
        sender, _beneficiary, _amount = proxy.pendingRequests(request_id)
        if sender == "0x0000000000000000000000000000000000000000":
            return True
        time.sleep(poll_sec)
    return False


def _load_testing_sender():
    sender_key = _require_env("TESTING_SENDER_PRIV_KEY")
    return accounts.add(sender_key)


def main(
    proxy_address=None,
    users_csv=None,
    amount_eth="0.001",
    timeout_sec="240",
    poll_sec="10",
):
    load_dotenv()

    if not proxy_address:
        proxy_address = _require_env("PARTNER_PROXY_ADDRESS")

    if not users_csv:
        users_csv = _require_env("PARTNER_USERS_CSV")

    users = _parse_users(users_csv)
    if not users:
        raise ValueError("No user addresses provided")

    amount_wei = Wei(f"{amount_eth} ether")
    timeout_sec = int(timeout_sec)
    poll_sec = int(poll_sec)

    proxy = ServiceDepositProxy.at(proxy_address)
    testing_sender = _load_testing_sender()
    beneficiary = users[0]

    print(f"Active network: {network.show_active()}")
    print(f"Proxy: {proxy.address}")
    print(f"Router: {proxy.router()}")
    print(f"MIN_RATING: {proxy.MIN_RATING()}")
    print(f"Testing sender: {testing_sender.address}")
    print(f"Target beneficiary: {beneficiary}")
    print(f"Amount (wei): {amount_wei}")
    print(f"Users checked: {len(users)}")

    if not proxy.partnerUsers(beneficiary):
        raise ValueError(f"Beneficiary {beneficiary} is not configured in partner proxy")

    tx = proxy.depositFor(beneficiary, {"from": testing_sender, "value": amount_wei})
    print(f"Deposit tx: {tx.txid}")

    request_id = _extract_request_id(tx)
    if not request_id:
        raise ValueError("Could not extract requestId from tx events")
    print(f"Request ID: {request_id.hex()}")

    fulfilled = _wait_for_fulfillment(proxy, request_id, timeout_sec, poll_sec)
    print(f"Fulfilled: {fulfilled}")

    print("\n--- Testing sender rate state ---")
    _print_user_state(proxy, testing_sender.address)

    print("\n--- Beneficiary balances ---")
    for user in users:
        print(f"user: {user}")
        print(f"  partnerAllowed: {proxy.partnerUsers(user)}")
        print(f"  credited:       {proxy.balances(user)}")
