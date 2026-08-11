"""
Single source of truth for resolving the deployed IoTDataRegistry address.

WHY THIS MODULE EXISTS
----------------------
The address is not configured anywhere. It is derived from the truffle build
artifact, which truffle rewrites on every `migrate` and never prunes — the
artifact currently carries 18 network entries, all stale but one.

Before this module there were two resolvers with DIFFERENT rules:

    orchestrator.py   list(artifact['networks'].keys())[-1]   last in file order
    exp3_gas_real.py  max(networks, key=int)                  highest network id

They agree only by coincidence. When they diverge, exp3 measures gas against one
contract while exp1 and exp5 anchor to another — inside what the paper presents
as a single consolidated run. Nothing in the pipeline would flag it.

THE RULE
--------
Highest numeric network id wins. Ganache assigns a timestamp-based network id
when one is not pinned, so "highest" means "most recently deployed". Pinning
`--networkId 1337` collapses this to a single entry, which is the recommended
setup (see STACK_BRINGUP.md §B) — the rule then becomes trivially unambiguous.

Callers that hold a live web3 connection should pass it so the resolver can
verify that code actually exists at the address. An address with no bytecode
behind it is a stale artifact entry, and every downstream transaction against it
fails later and less legibly.
"""

import json
from typing import Any, Dict, Optional, Tuple


class ContractResolutionError(RuntimeError):
    """The deployed contract address could not be resolved, or is stale."""


def load_artifact(artifact_path: str) -> Dict[str, Any]:
    with open(artifact_path) as f:
        return json.load(f)


def select_network(networks: Dict[str, Any]) -> Tuple[str, str]:
    """Pick (network_id, address) by highest numeric network id.

    This is THE rule. Do not re-implement selection anywhere else.
    """
    if not networks:
        raise ContractResolutionError(
            "contract artifact has no 'networks' entries — the contract has never "
            "been deployed against any chain. Run: npx truffle migrate "
            "--network development --reset")
    numeric = {k: v for k, v in networks.items() if str(k).isdigit()}
    if not numeric:
        raise ContractResolutionError(
            f"contract artifact has no numeric network ids (got {list(networks)})")
    nid = max(numeric, key=int)
    entry = numeric[nid]
    if not entry.get("address"):
        raise ContractResolutionError(
            f"network entry {nid} in the artifact carries no address")
    return nid, entry["address"]


def resolve(artifact_path: str, w3: Optional[Any] = None,
            require_code: bool = True) -> Dict[str, Any]:
    """Resolve the contract for this run.

    Returns {address, network_id, abi, chain_id, code_size}.

    With `w3` supplied and require_code=True (the default), raises
    ContractResolutionError when the selected address holds no bytecode — i.e.
    the artifact is stale relative to the chain that is actually running, which
    is what happens whenever Ganache is restarted without a redeploy.
    """
    artifact = load_artifact(artifact_path)
    nid, address = select_network(artifact.get("networks", {}))

    out = {
        "address": address,
        "network_id": nid,
        "abi": artifact["abi"],
        "artifact_path": artifact_path,
        "networks_in_artifact": len(artifact.get("networks", {})),
        "chain_id": None,
        "code_size": None,
    }

    if w3 is None:
        return out

    address = w3.to_checksum_address(address)
    out["address"] = address
    try:
        out["chain_id"] = w3.eth.chain_id
        code = w3.eth.get_code(address)
    except Exception as e:
        raise ContractResolutionError(
            f"cannot reach the chain to verify {address}: {e}")
    out["code_size"] = len(code)

    if require_code and len(code) <= 2:
        raise ContractResolutionError(
            f"no contract code at {address} (network id {nid}, selected from "
            f"{out['networks_in_artifact']} artifact entries).\n"
            f"The artifact is stale relative to the running chain — this is what a "
            f"Ganache restart without a redeploy looks like.\n"
            f"Fix: npx truffle migrate --network development --reset, then restart "
            f"this process. See STACK_BRINGUP.md section B.")

    return out
