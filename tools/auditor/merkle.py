"""Keccak-256 Merkle trees (manuscript Eq. 13a/13b), shared by the auditor and exp3.

Leaves are 32-byte digests (in OrBIT, h_i = H(m_i)). Internal node = keccak(left
|| right). An odd node at any level is paired with itself. A proof is the list of
(sibling, side) pairs from leaf to root, side 'L' when the sibling is on the left.
Standard library + eth_utils only.
"""
from eth_utils import keccak


def _b(x):
    if isinstance(x, (bytes, bytearray)):
        return bytes(x)
    s = x[2:] if x.startswith("0x") else x
    return bytes.fromhex(s)


def build(leaves):
    """Return the list of levels, leaves first, root last (each a list of bytes)."""
    level = [_b(x) for x in leaves]
    if not level:
        raise ValueError("empty tree")
    levels = [level]
    while len(level) > 1:
        level = [keccak(level[i] + (level[i + 1] if i + 1 < len(level) else level[i]))
                 for i in range(0, len(level), 2)]
        levels.append(level)
    return levels


def root(leaves):
    return "0x" + build(leaves)[-1][0].hex()


def proof(leaves, index):
    """Inclusion proof for leaves[index]: [(sibling_hex, 'L'|'R'), ...]."""
    out = []
    for level in build(leaves)[:-1]:
        sib = index ^ 1
        sib_node = level[sib] if sib < len(level) else level[index]
        out.append(("0x" + sib_node.hex(), "L" if sib < index else "R"))
        index //= 2
    return out


def verify(leaf, proof_, root_):
    """VerifyMerkle(R, H(m_j), pi_j) of Eq. 13b."""
    node = _b(leaf)
    for sib, side in proof_:
        node = keccak(_b(sib) + node) if side == "L" else keccak(node + _b(sib))
    return node == _b(root_)
