"""Test utilities for generating genuine cryptographic WebAuthn registrations and assertions."""

import hashlib
import json
import struct
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url, encode_cbor


def generate_test_keypair():
    """Generate an EC P-256 key pair and return (private_key, cose_key_bytes, public_key_b64)."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    cose_key = {
        1: 2,   # kty: EC2
        3: -7,  # alg: ES256
        -1: 1,  # crv: P-256
        -2: public_numbers.x.to_bytes(32, 'big'),
        -3: public_numbers.y.to_bytes(32, 'big'),
    }
    cose_key_bytes = encode_cbor(cose_key)
    public_key_b64 = bytes_to_base64url(cose_key_bytes)
    return private_key, cose_key_bytes, public_key_b64


def make_registration_response(
    challenge_b64: str,
    credential_id: bytes = b'test_cred_id_123',
    origin: str = 'http://testserver',
    rp_id: str = 'testserver',
    private_key=None,
):
    """Generate a genuine WebAuthn registration credential payload with valid attestationObject."""
    if private_key is None:
        private_key, cose_key_bytes, _ = generate_test_keypair()
    else:
        public_numbers = private_key.public_key().public_numbers()
        cose_key = {
            1: 2,
            3: -7,
            -1: 1,
            -2: public_numbers.x.to_bytes(32, 'big'),
            -3: public_numbers.y.to_bytes(32, 'big'),
        }
        cose_key_bytes = encode_cbor(cose_key)

    client_data = json.dumps({'type': 'webauthn.create', 'challenge': challenge_b64, 'origin': origin})
    client_data_b64 = bytes_to_base64url(client_data.encode('utf-8'))

    rp_id_hash = hashlib.sha256(rp_id.encode('utf-8')).digest()
    flags = bytes([0x41])  # UP (User Present) + AT (Attested Credential Data Present)
    sign_count = struct.pack('>I', 0)
    aaguid = b'\x00' * 16
    cred_id_len = struct.pack('>H', len(credential_id))
    auth_data = rp_id_hash + flags + sign_count + aaguid + cred_id_len + credential_id + cose_key_bytes

    attestation_obj = {
        'fmt': 'none',
        'attStmt': {},
        'authData': auth_data,
    }
    attestation_b64 = bytes_to_base64url(encode_cbor(attestation_obj))

    cred_id_b64 = bytes_to_base64url(credential_id)
    return {
        'id': cred_id_b64,
        'rawId': cred_id_b64,
        'type': 'public-key',
        'response': {
            'clientDataJSON': client_data_b64,
            'attestationObject': attestation_b64,
        }
    }, private_key, bytes_to_base64url(cose_key_bytes)


def make_assertion_response(
    private_key,
    challenge_b64: str,
    credential_id: bytes = b'test_cred_id_123',
    origin: str = 'http://testserver',
    rp_id: str = 'testserver',
    sign_count: int = 1,
    tamper_signature: bool = False,
    op_type: str = 'webauthn.get',
):
    """Generate a genuine WebAuthn assertion response signed with the private key."""
    client_data = json.dumps({'type': op_type, 'challenge': challenge_b64, 'origin': origin})
    client_data_bytes = client_data.encode('utf-8')
    client_data_b64 = bytes_to_base64url(client_data_bytes)

    rp_id_hash = hashlib.sha256(rp_id.encode('utf-8')).digest()
    flags = bytes([0x01])  # UP (User Present)
    auth_data = rp_id_hash + flags + struct.pack('>I', sign_count)
    auth_data_b64 = bytes_to_base64url(auth_data)

    sig_data = auth_data + hashlib.sha256(client_data_bytes).digest()
    signature = private_key.sign(sig_data, ec.ECDSA(hashes.SHA256()))
    if tamper_signature:
        signature = bytes([b ^ 0xFF for b in signature])
    sig_b64 = bytes_to_base64url(signature)

    cred_id_b64 = bytes_to_base64url(credential_id)
    return {
        'id': cred_id_b64,
        'rawId': cred_id_b64,
        'type': 'public-key',
        'response': {
            'clientDataJSON': client_data_b64,
            'authenticatorData': auth_data_b64,
            'signature': sig_b64,
        }
    }
