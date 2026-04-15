import argparse
import base64
import json
import os
import random
import time
from pathlib import Path
from typing import List
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv


MESSAGE_ID_MAX_LEN = 128
MESSAGE_METHOD_MAX_LEN = 64
MESSAGE_DON_ID_MAX_LEN = 64
MESSAGE_RECEIVER_LEN = 42  # 0x + 40 hex chars
DEFAULT_GATEWAY_URLS = (
    "https://01.functions-gateway.testnet.chain.link,"
    "https://02.functions-gateway.testnet.chain.link"
)


def _pad_bytes(value: str, length: int) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > length:
        raise ValueError(f"Value '{value}' is longer than max length {length}")
    return raw + b"\x00" * (length - len(raw))


def _require(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _gateway_message_body(message_id: str, method: str, don_id: str, receiver: str, payload: dict) -> bytes:
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return b"".join(
        [
            _pad_bytes(message_id, MESSAGE_ID_MAX_LEN),
            _pad_bytes(method, MESSAGE_METHOD_MAX_LEN),
            _pad_bytes(don_id, MESSAGE_DON_ID_MAX_LEN),
            _pad_bytes(receiver, MESSAGE_RECEIVER_LEN),
            payload_json,
        ]
    )


def _sign_eip191_bytes(private_key_hex: str, payload_bytes: bytes) -> str:
    acct = Account.from_key(private_key_hex)
    signed = acct.sign_message(encode_defunct(payload_bytes))
    return signed.signature.hex().removeprefix("0x")


def _build_payload(private_key_hex: str, slot_id: int, encrypted_secrets_hex: str, minutes_until_expiration: int):
    if not encrypted_secrets_hex.startswith("0x"):
        raise ValueError("encrypted_secrets_hex must start with 0x")

    acct = Account.from_key(private_key_hex)
    signer_address = acct.address
    signer_address_base64 = base64.b64encode(bytes.fromhex(signer_address[2:])).decode()
    encrypted_secrets_base64 = base64.b64encode(bytes.fromhex(encrypted_secrets_hex[2:])).decode()

    secrets_version = int(time.time())
    secrets_expiration = int(time.time() * 1000) + minutes_until_expiration * 60 * 1000

    message = {
        "address": signer_address_base64,
        "slotid": slot_id,
        "payload": encrypted_secrets_base64,
        "version": secrets_version,
        "expiration": secrets_expiration,
    }
    message_json = json.dumps(message, separators=(",", ":"), ensure_ascii=False)

    storage_sig_hex = _sign_eip191_bytes(private_key_hex, message_json.encode("utf-8"))
    storage_signature_base64 = base64.b64encode(bytes.fromhex(storage_sig_hex)).decode()

    payload = {
        "slot_id": slot_id,
        "version": secrets_version,
        "payload": encrypted_secrets_base64,
        "expiration": secrets_expiration,
        "signature": storage_signature_base64,
    }
    return payload, secrets_version


def _send_to_gateway(gateway_url: str, private_key_hex: str, don_id: str, payload: dict):
    # Match toolkit behavior: random uint32 represented as string.
    message_id = str(random.randint(0, (2**32) - 1))
    method = "secrets_set"
    receiver = ""

    body = {
        "message_id": message_id,
        "method": method,
        "don_id": don_id,
        "receiver": receiver,
        "payload": payload,
    }

    gateway_message_bytes = _gateway_message_body(message_id, method, don_id, receiver, payload)
    gateway_sig_hex = _sign_eip191_bytes(private_key_hex, gateway_message_bytes)
    gateway_signature = "0x" + gateway_sig_hex

    req = {
        "id": message_id,
        "jsonrpc": "2.0",
        "method": method,
        "params": {
            "body": body,
            "signature": gateway_signature,
        },
    }

    req_json = json.dumps(req, separators=(",", ":"), ensure_ascii=False)
    curl_cmd = (
        f"curl -X POST \"{gateway_url}\" "
        f"-H \"Content-Type: application/json\" "
        f"--data-raw '{req_json}'"
    )
    print("\n[DEBUG] Gateway request curl:")
    print(curl_cmd)

    response = requests.post(
        gateway_url,
        data=req_json.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise RuntimeError(f"HTTP {response.status_code} from {gateway_url}: {body}")
    return response.json()


def _parse_gateways(raw: str) -> List[str]:
    gateways = []
    for item in raw.split(","):
        url = item.strip()
        if not url:
            continue
        gateways.append(url)
    return gateways


def _normalize_hex_or_file(value: str, base_dir: Path) -> str:
    raw = (value or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("encrypted secrets hex is empty")

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    if candidate.exists() and candidate.is_file():
        raw = candidate.read_text(encoding="utf-8").strip()

    if not raw.startswith("0x"):
        raw = "0x" + raw
    return raw


def main():
    # Load .env from project root (parent of scripts/)
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    parser = argparse.ArgumentParser(
        description="Upload encrypted DON-hosted secrets using gateway method secrets_set."
    )
    parser.add_argument(
        "--private-key",
        default=os.getenv("CHAINLINK_SECRETS_UPLOADER_PRIVATE_KEY", os.getenv("DEPLOYER_PRIVATE_KEY")),
        help="Private key used to sign storage and gateway messages",
    )
    parser.add_argument("--don-id", default=os.getenv("CHAINLINK_DON_ID_TEXT", "fun-ethereum-sepolia-1"))
    parser.add_argument("--gateway-urls", default=os.getenv("CHAINLINK_GATEWAY_URLS", DEFAULT_GATEWAY_URLS))
    parser.add_argument("--slot-id", type=int, default=int(os.getenv("CHAINLINK_SECRETS_SLOT_ID", "0")))
    parser.add_argument("--minutes-until-expiration", type=int, default=int(os.getenv("CHAINLINK_SECRETS_TTL_MIN", "60")))
    parser.add_argument(
        "--encrypted-secrets-hex",
        default=os.getenv("CHAINLINK_ENCRYPTED_SECRETS_HEX", ""),
        help="Hex string from Functions toolkit encryptSecrets/upload flow (0x...).",
    )
    args = parser.parse_args()

    private_key = _require(args.private_key, "private key")
    don_id = _require(args.don_id, "don id")
    gateways = _parse_gateways(_require(args.gateway_urls, "gateway urls"))
    encrypted_hex_input = _require(args.encrypted_secrets_hex, "encrypted secrets hex")
    encrypted_hex = _normalize_hex_or_file(encrypted_hex_input, project_root)
    signer_address = Account.from_key(private_key).address

    payload, version = _build_payload(
        private_key,
        args.slot_id,
        encrypted_hex,
        args.minutes_until_expiration,
    )

    print(f"signer_address={signer_address}")
    print(f"slot_id={args.slot_id}")
    print(f"version={version}")
    print(f"don_id={don_id}")
    print(f"gateways={len(gateways)}")

    last_ok = None
    for gw in gateways:
        try:
            result = _send_to_gateway(gw, private_key, don_id, payload)
            print(f"[OK] {gw}")
            print(json.dumps(result, indent=2))
            last_ok = result
            break
        except Exception as exc:
            print(f"[FAIL] {gw}: {exc}")

    if not last_ok:
        raise RuntimeError("Failed to send secrets_set to all gateways")

    print("\nDone.")
    print("Use slot_id/version in router config per partner proxy.")


if __name__ == "__main__":
    main()
