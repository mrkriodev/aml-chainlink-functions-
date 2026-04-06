import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from coincurve import PrivateKey, PublicKey
from Crypto.Cipher import AES
from ecdsa import NIST256p, ellipticcurve
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from web3 import Web3


TDH2_INPUT_SIZE = 32
GROUP_NAME = "P256"

ROUTER_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "id", "type": "bytes32"}],
        "name": "getContractById",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

COORDINATOR_ABI = [
    {
        "inputs": [],
        "name": "getThresholdPublicKey",
        "outputs": [{"internalType": "bytes", "name": "", "type": "bytes"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getDONPublicKey",
        "outputs": [{"internalType": "bytes", "name": "", "type": "bytes"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _load_secrets_map(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict) or not data:
        raise ValueError("Secrets JSON must be a non-empty object map")
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Secrets JSON must be string->string map")
    return data


def _sign_message_text(private_key_hex: str, message_text: str) -> str:
    acct = Account.from_key(private_key_hex)
    signed = acct.sign_message(encode_defunct(text=message_text))
    return signed.signature.hex().removeprefix("0x")


def _format_bytes32_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > 32:
        raise ValueError("don id must be <= 32 bytes")
    return raw + b"\x00" * (32 - len(raw))


def _fetch_don_keys(rpc_url: str, functions_router_address: str, don_id_text: str):
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ValueError("web3 connection failed")

    router = w3.eth.contract(address=Web3.to_checksum_address(functions_router_address), abi=ROUTER_ABI)
    don_id_bytes32 = _format_bytes32_string(don_id_text)
    coordinator_address = router.functions.getContractById(don_id_bytes32).call()

    coordinator = w3.eth.contract(address=Web3.to_checksum_address(coordinator_address), abi=COORDINATOR_ABI)
    threshold_public_key_bytes = coordinator.functions.getThresholdPublicKey().call()
    don_public_key_hex = coordinator.functions.getDONPublicKey().call().hex()

    threshold_public_key = json.loads(bytes(threshold_public_key_bytes).decode("utf-8"))
    return coordinator_address, threshold_public_key, don_public_key_hex


def _ensure_uncompressed_pubkey_65(pub_hex: str) -> bytes:
    clean = pub_hex.removeprefix("0x")
    raw = bytes.fromhex(clean)
    if len(raw) == 64:
        return b"\x04" + raw
    if len(raw) == 65 and raw[0] == 0x04:
        return raw
    if len(raw) == 33:
        return PublicKey(raw).format(compressed=False)
    raise ValueError("Unsupported public key length for DON public key")


def _ethcrypto_encrypt_with_public_key(public_key_hex: str, message: bytes) -> str:
    recipient_pub_uncompressed = _ensure_uncompressed_pubkey_65(public_key_hex)
    recipient_pub = PublicKey(recipient_pub_uncompressed)

    ephem_priv = PrivateKey()
    ephem_pub_uncompressed = ephem_priv.public_key.format(compressed=False)

    # shared secret x-coordinate (32 bytes) for ECIES KDF compatibility
    shared_point_uncompressed = recipient_pub.multiply(ephem_priv.secret).format(compressed=False)
    shared_secret = shared_point_uncompressed[1:33]

    kdf_hash = hashlib.sha512(shared_secret).digest()
    enc_key = kdf_hash[:32]
    mac_key = kdf_hash[32:]

    iv = secrets.token_bytes(16)
    aes = AES.new(enc_key, AES.MODE_CBC, iv=iv)
    pad_len = 16 - (len(message) % 16)
    padded = message + bytes([pad_len]) * pad_len
    ciphertext = aes.encrypt(padded)

    mac = hmac.new(mac_key, iv + ephem_pub_uncompressed + ciphertext, hashlib.sha256).digest()
    ephem_pub_compressed = PublicKey(ephem_pub_uncompressed).format(compressed=True)

    # EthCrypto.cipher.stringify layout:
    # iv(16) + ephemPublicKeyCompressed(33) + mac(32) + ciphertext(var)
    return (iv + ephem_pub_compressed + mac + ciphertext).hex()


def _decode_p256_point_b64(point_b64: str):
    point_bytes = base64.b64decode(point_b64)
    return ellipticcurve.Point.from_bytes(NIST256p.curve, point_bytes, validate_encoding=True)


def _encode_p256_point_b64(point) -> str:
    point_bytes = ellipticcurve.Point.to_bytes(point, encoding="uncompressed")
    return base64.b64encode(point_bytes).decode("utf-8")


def _concatenate_points(points) -> bytes:
    out = GROUP_NAME
    for p in points:
        out += "," + ellipticcurve.Point.to_bytes(p, encoding="uncompressed").hex()
    return out.encode("utf-8")


def _hash1(point) -> bytes:
    return hashlib.sha256(b"tdh2hash1" + _concatenate_points([point])).digest()


def _hash2(msg: bytes, label: bytes, p1, p2, p3, p4) -> int:
    if len(msg) != TDH2_INPUT_SIZE:
        raise ValueError("msg must be 32 bytes")
    if len(label) != TDH2_INPUT_SIZE:
        raise ValueError("label must be 32 bytes")

    digest = hashlib.sha256(
        b"tdh2hash2" + msg + label + _concatenate_points([p1, p2, p3, p4])
    ).digest()
    return int.from_bytes(digest, "big") % NIST256p.order


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    if len(a) != len(b):
        raise ValueError("xor length mismatch")
    return bytes(x ^ y for x, y in zip(a, b))


def _tdh2_encrypt(pub: dict, msg32: bytes, label32: bytes) -> str:
    if pub.get("Group") != GROUP_NAME:
        raise ValueError("invalid TDH2 group")
    if len(msg32) != TDH2_INPUT_SIZE or len(label32) != TDH2_INPUT_SIZE:
        raise ValueError("TDH2 input size must be 32 bytes")

    g_bar = _decode_p256_point_b64(pub["G_bar"])
    h_point = _decode_p256_point_b64(pub["H"])

    n = NIST256p.order
    G = NIST256p.generator
    r = secrets.randbelow(n - 1) + 1
    s = secrets.randbelow(n - 1) + 1

    c = _xor_bytes(_hash1(h_point * r), msg32)
    u = G * r
    w = G * s
    u_bar = g_bar * r
    w_bar = g_bar * s

    e = _hash2(c, label32, u, w, u_bar, w_bar)
    f = (s + (r * e) % n) % n

    out = {
        "Group": GROUP_NAME,
        "C": base64.b64encode(c).decode("utf-8"),
        "Label": base64.b64encode(label32).decode("utf-8"),
        "U": _encode_p256_point_b64(u),
        "U_bar": _encode_p256_point_b64(u_bar),
        "E": base64.b64encode(e.to_bytes(32, "big")).decode("utf-8"),
        "F": base64.b64encode(f.to_bytes(32, "big")).decode("utf-8"),
    }
    return _canonical_json(out)


def _tdh2_hybrid_encrypt(pub: dict, plaintext: bytes) -> str:
    key = secrets.token_bytes(TDH2_INPUT_SIZE)
    nonce = secrets.token_bytes(12)

    aes = AES.new(key, AES.MODE_GCM, nonce=nonce)
    sym_ctxt, tag = aes.encrypt_and_digest(plaintext)
    tdh2_ctxt_json = _tdh2_encrypt(pub, key, b"\x00" * TDH2_INPUT_SIZE)

    out = {
        "TDH2Ctxt": base64.b64encode(tdh2_ctxt_json.encode("utf-8")).decode("utf-8"),
        "SymCtxt": base64.b64encode(sym_ctxt + tag).decode("utf-8"),
        "Nonce": base64.b64encode(nonce).decode("utf-8"),
    }
    return _canonical_json(out)


def main():
    # Load .env from project root (parent of scripts/)
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    parser = argparse.ArgumentParser(
        description="Pure-Python full encryptSecrets-compatible chain: sign -> ECIES -> TDH2."
    )
    parser.add_argument("--secrets-json", default=os.getenv("CHAINLINK_SECRETS_JSON", "test_sec.json"))
    parser.add_argument("--private-key", default=os.getenv("DEPLOYER_PRIVATE_KEY", ""))
    parser.add_argument("--rpc-url", default=os.getenv("WEB3_RPC_URL", os.getenv("CHAINLINK_RPC_URL", "")))
    parser.add_argument("--functions-router-address", default=os.getenv("CHAINLINK_ROUTER_ADDRESS", ""))
    parser.add_argument("--don-id", default=os.getenv("CHAINLINK_DON_ID_TEXT", "fun-ethereum-sepolia-1"))
    parser.add_argument("--out-prefix", default=os.getenv("CHAINLINK_ENC_OUT_PREFIX", "enc_artifacts"))
    args = parser.parse_args()

    if not args.private_key:
        raise ValueError("private key is required")
    if not args.rpc_url:
        raise ValueError("rpc url is required")
    if not args.functions_router_address:
        raise ValueError("functions router address is required")

    secrets_json_path = Path(args.secrets_json)
    if not secrets_json_path.is_absolute():
        secrets_json_path = project_root / secrets_json_path
    secrets_map = _load_secrets_map(str(secrets_json_path))
    message = _canonical_json(secrets_map)
    signature = _sign_message_text(args.private_key, message)
    signed_secrets_json = _canonical_json({"message": message, "signature": "0x" + signature})

    coordinator_address, threshold_pub, don_pub_hex = _fetch_don_keys(
        args.rpc_url, args.functions_router_address, args.don_id
    )
    encrypted_signed_hex = _ethcrypto_encrypt_with_public_key(don_pub_hex, signed_secrets_json.encode("utf-8"))
    don_key_encrypted = {"0x0": base64.b64encode(bytes.fromhex(encrypted_signed_hex)).decode("utf-8")}
    encrypted_secrets_json = _tdh2_hybrid_encrypt(threshold_pub, _canonical_json(don_key_encrypted).encode("utf-8"))
    encrypted_secrets_hex = "0x" + encrypted_secrets_json.encode("utf-8").hex()

    out_prefix = Path(args.out_prefix)
    if not out_prefix.is_absolute():
        out_prefix = project_root / out_prefix
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    (out_prefix.with_suffix(".signed_secrets.json")).write_text(signed_secrets_json, encoding="utf-8")
    (out_prefix.with_suffix(".don_key_encrypted.json")).write_text(
        _canonical_json(don_key_encrypted), encoding="utf-8"
    )
    (out_prefix.with_suffix(".encrypted_secrets.json")).write_text(encrypted_secrets_json, encoding="utf-8")
    (out_prefix.with_suffix(".encrypted_secrets.hex.txt")).write_text(encrypted_secrets_hex, encoding="utf-8")

    print(f"Coordinator: {coordinator_address}")
    print(f"DON ID: {args.don_id}")
    print(f"Signed secrets: {out_prefix.with_suffix('.signed_secrets.json')}")
    print(f"DON-key encrypted payload: {out_prefix.with_suffix('.don_key_encrypted.json')}")
    print(f"TDH2 encrypted JSON: {out_prefix.with_suffix('.encrypted_secrets.json')}")
    print(f"encryptedSecretsHexstring: {encrypted_secrets_hex}")
    print("\nPass this to upload_don_secrets.py as --encrypted-secrets-hex")


if __name__ == "__main__":
    main()
