import sys
from pathlib import Path as _Path

# Allow running this file directly: `python3 scripts/upload_don_secrets.py`
# by ensuring `browniedir/` is on sys.path so `import scripts.*` works.
_project_root = _Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import argparse
import json
import os
from eth_account import Account
from dotenv import load_dotenv

from scripts.don_secrets_uploader import (
    DEFAULT_GATEWAY_URLS,
    parse_gateway_urls,
    upload_encrypted_secrets_to_don,
)

def _require(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def main():
    # Load .env from project root (parent of scripts/)
    project_root = _project_root
    load_dotenv(project_root / ".env")

    parser = argparse.ArgumentParser(
        description="Upload encrypted DON-hosted secrets using gateway method secrets_set."
    )
    parser.add_argument("--private-key", default=os.getenv("DEPLOYER_PRIVATE_KEY"))
    parser.add_argument("--don-id", default=os.getenv("CHAINLINK_DON_ID_TEXT", "fun-ethereum-sepolia-1"))
    parser.add_argument(
        "--gateway-urls",
        default=os.getenv("CHAINLINK_GATEWAY_URLS", ",".join(DEFAULT_GATEWAY_URLS)),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=(os.getenv("CHAINLINK_SECRETS_DEBUG", "").lower() in ("1", "true", "yes", "on")),
        help="Print full gateway HTTP responses (status, headers, body).",
    )
    parser.add_argument("--slot-id", type=int, default=int(os.getenv("CHAINLINK_SECRETS_SLOT_ID", "0")))
    parser.add_argument(
        "--message-id",
        default=os.getenv("CHAINLINK_SECRETS_MESSAGE_ID", ""),
        help="Optional fixed gateway message_id (uint32 string). If omitted, a random uint32 is used.",
    )
    parser.add_argument(
        "--version",
        default=os.getenv("CHAINLINK_SECRETS_VERSION", ""),
        help="Optional fixed secrets version (uint32 unix seconds). If omitted, uses current time.",
    )
    parser.add_argument(
        "--expiration-ms",
        default=os.getenv("CHAINLINK_SECRETS_EXPIRATION_MS", ""),
        help="Optional fixed secrets expiration (unix ms). If omitted, computed from now + minutesUntilExpiration.",
    )
    parser.add_argument("--minutes-until-expiration", type=int, default=int(os.getenv("CHAINLINK_SECRETS_TTL_MIN", "60")))
    parser.add_argument(
        "--encrypted-secrets-hex",
        default=os.getenv("CHAINLINK_ENCRYPTED_SECRETS_HEX", ""),
        help="Hex string from Functions toolkit encryptSecrets/upload flow (0x...).",
    )
    args = parser.parse_args()

    private_key = _require(args.private_key, "private key")
    don_id = _require(args.don_id, "don id")
    encrypted_hex_input = _require(args.encrypted_secrets_hex, "encrypted secrets hex")
    signer_address = Account.from_key(private_key).address

    version_override = int(args.version) if args.version else None
    expiration_ms_override = int(args.expiration_ms) if args.expiration_ms else None

    print(f"signer_address={signer_address}")
    print(f"slot_id={args.slot_id}")
    print(f"don_id={don_id}")
    gateways = parse_gateway_urls(_require(args.gateway_urls, "gateway urls"))
    print(f"gateways={len(gateways)}")

    summary = upload_encrypted_secrets_to_don(
        private_key_hex=private_key,
        don_id=don_id,
        gateway_urls=gateways,
        slot_id=args.slot_id,
        encrypted_secrets_hex_or_path=encrypted_hex_input,
        minutes_until_expiration=args.minutes_until_expiration,
        message_id=args.message_id.strip() or None,
        version_override=version_override,
        expiration_ms_override=expiration_ms_override,
        base_dir=project_root,
        debug=args.debug,
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\nDone.")
    print("Use slot_id/version in router config per partner proxy.")


if __name__ == "__main__":
    main()
