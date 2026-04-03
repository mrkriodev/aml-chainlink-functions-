import os
import time

from brownie import RatingGateSecure, Wei, accounts, network
from dotenv import load_dotenv


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _require_env(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not set in .env")
    return value


def _load_test_account():
    #key_one = os.getenv("MY_ADR_WORK_ONE_PRIVE_KEY") or os.getenv("MY_ADR_WORK_ONE_PRIV_KEY")
    key_two = os.getenv("MY_ADR_WORK_TWO_PRIVE_KEY") or os.getenv("MY_ADR_WORK_TWO_PRIV_KEY")

    if not key_two:
        raise ValueError("MY_ADR_WORK_TWO_PRIVE_KEY (or MY_ADR_WORK_TWO_PRIV_KEY) is not set in .env")

    return accounts.add(key_two)


def _extract_request_id(tx):
    if "RequestSent" not in tx.events:
        return None
    event = tx.events["RequestSent"]
    if isinstance(event, list):
        entry = event[-1]
    else:
        entry = event
    if "requestId" in entry:
        return entry["requestId"]
    if "id" in entry:
        return entry["id"]
    return None


def _wait_for_fulfillment(contract, request_id, timeout_sec, poll_sec):
    started = time.time()
    while (time.time() - started) < timeout_sec:
        user, _amount = contract.pendingRequests(request_id)
        if user == ZERO_ADDRESS:
            return True
        time.sleep(poll_sec)
    return False


def _run_single_check(contract, sender, amount_wei, timeout_sec, poll_sec):
    print(f"Sender: {sender.address}")
    before_valid = contract.validUsers(sender.address)
    print(f"validUsers before: {before_valid}")

    tx = sender.transfer(contract.address, amount_wei)
    print(f"Funding tx: {tx.txid}")

    request_id = _extract_request_id(tx)
    if not request_id:
        print("No RequestSent event found. Request may have failed before emission.")
        return

    print(f"Request ID: {request_id.hex()}")
    fulfilled = _wait_for_fulfillment(contract, request_id, timeout_sec, poll_sec)
    print(f"Fulfilled: {fulfilled}")

    after_valid = contract.validUsers(sender.address)
    print(f"validUsers after: {after_valid}")
    if after_valid and not before_valid:
        print("Result: user accepted")
    elif not after_valid and before_valid:
        print("Result: user lost valid status (unexpected)")
    elif after_valid:
        print("Result: user remains accepted")
    else:
        print("Result: user not accepted (likely rejected/refunded)")


def main(contract_address=None, amount_eth="0.001", timeout_sec="240", poll_sec="10"):
    load_dotenv()

    if not contract_address:
        contract_address = _require_env("RATING_GATE_ADDRESS")

    amount_wei = Wei(f"{amount_eth} ether")
    timeout_sec = int(timeout_sec)
    poll_sec = int(poll_sec)

    contract = RatingGateSecure.at(contract_address)
    acc_one = _load_test_account()

    print(f"Active network: {network.show_active()}")
    print(f"Contract: {contract.address}")
    print(f"Amount (wei): {amount_wei}")
    print(f"Timeout seconds: {timeout_sec}, poll seconds: {poll_sec}")

    print("\n--- Check account one ---")
    _run_single_check(contract, acc_one, amount_wei, timeout_sec, poll_sec)

    # print("\n--- Check account two ---")
    # _run_single_check(contract, acc_two, amount_wei, timeout_sec, poll_sec)
