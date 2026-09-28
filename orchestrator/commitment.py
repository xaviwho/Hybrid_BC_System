"""
commitment.py - the commitment chain of manuscript Section III-D/E, in one place.

    m      public metadata: the policy engine's redacted view of x (Alg. 1 l.25)
    h      = H(m)                                         Eq. (12), Keccak-256
    sigma  = <id, k, nu, tau, h>                          Eq. (22)
    c      = H(sigma)                                     Eq. (20a), anchored

with, in this implementation,

    id   the idempotency key (content hash of x, or X-Idempotency-Key)
    k    the Fabric world-state key the record is stored under (= id)
    nu   the Fabric transaction id that created the record (read back, Alg. 1 l.22)
    tau  ingress time t0, integer microseconds since the epoch

Every hash is taken over canonical JSON: sorted keys, no whitespace, UTF-8,
NaN/Infinity rejected. Before v2 the anchored value was sha256(json.dumps(x))
over the FULL record, including sensitive fields, in non-canonical key order
(AUDIT_WS0 F2/F3). That leaked a brute-forceable digest of low-entropy
sensitive values and could not be recomputed by an auditor.

The WS5 auditor re-implements these rules independently. This module is the
orchestrator's copy, not the verifier's.
"""

import json

from eth_utils import keccak


def canon(obj):
    """Canonical JSON bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def h_hex(data):
    """Keccak-256 of bytes, 0x-prefixed hex."""
    return "0x" + keccak(data).hex()


def metadata_hash(m):
    """h = H(m)."""
    return h_hex(canon(m))


def make_sigma(record_id, key, nu, tau, h):
    return {"id": record_id, "k": key, "nu": nu, "tau": tau, "h": h}


def commitment(sigma):
    """c = H(sigma)."""
    return h_hex(canon(sigma))


def onchain_id(record_id):
    """bytes32 registry key for a record id: Keccak-256 of its UTF-8 bytes."""
    return keccak(record_id.encode("utf-8"))


def make_envelope(record_id, t0_us, x, m, h, route, sensitivity):
    """The bytes stored on Fabric. x is the FULL payload (Alg. 1 l.21)."""
    return canon({"id": record_id, "t0_us": t0_us, "x": x, "m": m, "h": h,
                  "route": route, "sensitivity": sensitivity}).decode("utf-8")
