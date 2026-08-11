# Stack Bring-Up — WSL2 host

Exact commands to bring the measurement stack up in dependency order, then run the
three experiments that need it (exp1, exp3, exp5).

Everything here is read from the repo or from `BRINGUP_STATUS.md`, which records
the last known-good bring-up (2026-07-01, Stage 3 gate passed). Anything I could
not determine from the repo is marked **UNVERIFIED**.

**The layout is unusual and you need to know it before starting.** Three
directories are in play:

| What | Where | Filesystem |
|------|-------|-----------|
| Repo (code, experiments, results) | `/mnt/e/Hybrid_BC_System` | **drvfs → FAT32 stick** |
| Fabric runtime (bins, config, test-network) | `/root/fabric-clean` | ext4 |
| Chaincode source used by `deployCC` | `/root/hybrid-fabric/chaincode/iot-data/go` | ext4 |
| Python venv for policy + orchestrator | `/root/orbit-venv` | ext4 |

The repo's own `blockchain/setup/hyperledger/fabric-samples` was found corrupted
during the last bring-up (three defects in the CA compose files) and replaced with
a pristine clone at `/root/fabric-clean`. **Do not run `./start-hybrid-network.sh`
or `./start-system.sh`** — they point at the repo copy on drvfs, which is the
configuration that never worked. Use the explicit commands below.

---

## 0. Preconditions

```bash
wsl -d Ubuntu-22.04 -u root
```

| Check | Command | Expect |
|-------|---------|--------|
| Docker reachable from WSL | `docker version --format '{{.Server.Version}}'` | a version string |
| Fabric runtime present | `ls /root/fabric-clean/bin/peer /root/fabric-clean/config` | both exist |
| Chaincode source present | `ls /root/hybrid-fabric/chaincode/iot-data/go/*.go` | at least one file |
| Repo mounted | `ls /mnt/e/Hybrid_BC_System/orchestrator/orchestrator.py` | exists |
| venv present | `ls /root/orbit-venv/bin/python` | exists |
| Go + jq | `go version && jq --version` | Go 1.18.x, jq 1.6 |

**If Docker is not reachable:** Docker Desktop → Settings → Resources → WSL
Integration → enable Ubuntu-22.04 → Apply & Restart. This was Blocker 1 last time.

**If `/mnt/e` is missing:**
```bash
mkdir -p /mnt/e && mount -t drvfs E: /mnt/e
```

**If `/root/fabric-clean` is missing** the network has to be rebuilt from a
pristine `fabric-samples` — see `BRINGUP_STATUS.md` "The bundled fabric-samples was
corrupted". Do not substitute the repo copy.

---

## 1. Hyperledger Fabric

```bash
cd /root/fabric-clean/test-network
export PATH=/root/fabric-clean/bin:/usr/bin:$PATH
export FABRIC_CFG_PATH=/root/fabric-clean/config
export IMAGE_TAG=2.5.0 CA_IMAGE_TAG=1.5.5

./network.sh up -ca -s couchdb -i 2.5.0 -cai 1.5.5
./network.sh createChannel -c hiot -ca -s couchdb -i 2.5.0 -cai 1.5.5
./network.sh deployCC -c hiot -ccn iot-data \
    -ccp /root/hybrid-fabric/chaincode/iot-data/go -ccl go
```

The image tags are not optional — an untagged CA image pulled `:latest` and broke
enrollment last time.

**Health check** — 8 containers, then a real round trip:

```bash
docker ps --format '{{.Names}}' | grep -cE 'orderer|peer0.org[12]|couchdb[01]|ca_'   # expect 8

export CORE_PEER_TLS_ENABLED=true CORE_PEER_LOCALMSPID=Org1MSP
ORG1=/root/fabric-clean/test-network/organizations/peerOrganizations/org1.example.com
export CORE_PEER_TLS_ROOTCERT_FILE=$ORG1/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=$ORG1/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=localhost:7051

peer chaincode query -C hiot -n iot-data -c '{"Args":["ReadIoTData","iot-777"]}'
```

Expect either the stored record or a clean "does not exist" error — both prove the
chaincode is committed and queryable. A TLS or connection error does not.

**If it fails**

| Symptom | Cause / fix |
|---------|-------------|
| Enrollment hangs at CA | The corrupted repo fabric-samples. Confirm you are in `/root/fabric-clean`, not `/mnt/e/...`. |
| `connection refused` to ca_orderer | Port mismatch (11054 vs 9054) — again the repo copy. |
| Channel exists from a previous run | `./network.sh down` then repeat from `network.sh up`. |
| `deployCC` cannot find chaincode | Check `-ccp` path; the chaincode lives at `/root/hybrid-fabric`, *not* under `fabric-clean`. |

---

## 2. Ganache

Ganache must run **inside WSL**. A Ganache on the Windows side is not reachable
from WSL (recorded in `BRINGUP_STATUS.md`).

```bash
cd /mnt/e/Hybrid_BC_System/blockchain/setup/ethereum
npx ganache --host 127.0.0.1 --port 8545 --chain.chainId 1337 \
            --wallet.deterministic --networkId 1337 \
            > /root/ganache.log 2>&1 &
```

`--networkId 1337` is an addition to what the compose file does — see §B below for
why it matters.

**Health check**

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
  http://127.0.0.1:8545
```

Expect `{"jsonrpc":"2.0","id":1,"result":"0x539"}` (0x539 = 1337).

**If it fails:** check `/root/ganache.log`; if port 8545 is taken,
`ss -lptn 'sport = :8545'`.

> **Do not use `docker-compose-hybrid.yml` for Ganache.** Its command is
> `npx ganache --host 0.0.0.0` with no chainId, no deterministic wallet and no
> networkId, and it attaches to an `external: true` network named `fabric_test`
> which the `/root/fabric-clean` network does not create. It also runs an
> `ethereum-deployer` container that re-migrates on every `up`.

---

## 3. Contract deployment

```bash
cd /mnt/e/Hybrid_BC_System/blockchain/setup/ethereum
npx truffle migrate --network development --reset
```

`truffle-config.js` targets `127.0.0.1:8545` with `network_id: "*"`.

**Health check** — the orchestrator resolves the address from the build artifact,
so verify the artifact, and that code actually exists at that address:

```bash
cd /mnt/e/Hybrid_BC_System
python3 - <<'PY'
import json
from web3 import Web3
a = json.load(open('blockchain/setup/ethereum/build/contracts/IoTDataRegistry.json'))
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
nid = list(a['networks'].keys())[-1]          # exactly what orchestrator.py:81 does
addr = Web3.to_checksum_address(a['networks'][nid]['address'])
print('orchestrator will use network', nid, '->', addr)
print('bytecode length at that address:', len(w3.eth.get_code(addr)))
print('networks recorded in artifact:', len(a['networks']))
PY
```

Bytecode length must be > 2. If it is `2` (`0x`), the address is stale — see §B.

---

## 4. Policy engine

```bash
cd /mnt/e/Hybrid_BC_System/ml
PORT=5011 PYTHONPATH=/mnt/e/Hybrid_BC_System/ml \
  /root/orbit-venv/bin/python privacy_filter/predict.py > /root/policy.log 2>&1 &
```

Port 5011 rather than the 5001 default: 5001 was occupied by an unrelated program
on this host, and still is — a probe during this session got `404 page not found`
from a foreign service on 5001. Verify before choosing:
`ss -lptn 'sport = :5001'`.

**Health check**

```bash
curl -s http://127.0.0.1:5011/health
```

Expect JSON containing `policy_version`. The route the orchestrator calls is
`POST /filter_data`.

**If it fails:** flask must be present in the venv
(`/root/orbit-venv/bin/python -c 'import flask'`). The Windows Python does not
have it; the repo venv `orchestrator/.venv` is a WSL Python 3.10.

---

## 5. Orchestrator

```bash
cd /mnt/e/Hybrid_BC_System/orchestrator

export PRIVACY_FILTER_URL=http://127.0.0.1:5011/filter_data
export GANACHE_URL=http://127.0.0.1:8545
export FABRIC_BIN=/root/fabric-clean/bin
export FABRIC_CFG_PATH=/root/fabric-clean/config
export FABRIC_TEST_NETWORK=/root/fabric-clean/test-network
export FABRIC_CHANNEL=hiot
export FABRIC_CC_NAME=iot-data
export OUTBOX_DB=/root/orbit-state/outbox.db      # see §A — do not skip this

mkdir -p /root/orbit-state
/root/orbit-venv/bin/python orchestrator.py > /root/orchestrator.log 2>&1 &
```

**Health checks**

```bash
curl -s http://127.0.0.1:5002/health        # {"status":"healthy","ethereum_connected":true}
curl -s http://127.0.0.1:5002/outbox_stats  # relay_running must be true
```

`ethereum_connected: false` means `GANACHE_URL` is wrong or Ganache died.
`relay_running: false` means the relay thread did not start — check the log for the
`Outbox relay worker started` line, and that `RELAY_DISABLED` is unset.

**End-to-end smoke test** (one sensitive record):

```bash
curl -s -X POST http://127.0.0.1:5002/ingest_data \
  -H 'Content-Type: application/json' \
  -d '{"id":"smoke-1","deviceId":"d1","temperature":36.7,"patientId":"P1","diagnosis":"x"}'
```

Expect **202** with `fabric_tx_id` set, `anchor_state: "pending"`, and an
`outbox_id`. Then:

```bash
curl -s http://127.0.0.1:5002/anchor_status/<outbox_id>
```

Expect `anchor_state: "delivered"` with an `eth_tx_hash` within a second or two.
If it stays `pending`, the relay cannot reach Ganache; if it goes `failed`, read
`last_error` in that response.

**If the private commit fails:** the orchestrator now returns **502** with
`"Private commit to Fabric failed"` rather than anchoring anyway. Check
`FABRIC_*` paths and rerun the §1 `peer chaincode query` health check.

---

## 6. Run the experiments

Order matters only in that exp1 and exp5 both drive the orchestrator.

```bash
cd /mnt/e/Hybrid_BC_System
export ORCHESTRATOR_URL=http://127.0.0.1:5002
export GANACHE_URL=http://127.0.0.1:8545
V=/root/orbit-venv/bin/python

$V experiments/exp1_latency_real.py     # exit 0 required; exit 2 = gate failure
$V experiments/exp3_gas_real.py         # 27 real transactions
$V experiments/exp5_exactly_once_real.py
$V experiments/exp7_hadc_real.py        # offline, but rerun here to record versions
$V experiments/consolidate_results.py   # must exit 0 with empty not_measured
```

exp1 exiting **2** means the reconciliation gate failed: it writes
`exp1_latency_real.FAILED.json` with the discrepancy and deliberately records no
throughput numbers. That is the gate working — investigate, do not rerun until
it passes.

---

# The three things to check

## A. `outbox.db` lands on FAT32 — this will break WAL

**Default path:** `orchestrator.py:137`

```python
OUTBOX_DB = os.getenv("OUTBOX_DB", os.path.join(os.path.dirname(__file__), "outbox.db"))
```

`os.path.dirname(__file__)` is the orchestrator package directory. Run as
documented, that resolves to **`/mnt/e/Hybrid_BC_System/orchestrator/outbox.db`**
— on the drvfs-mounted FAT32 stick, per `BRINGUP_STATUS.md`: *"Relocated Fabric
runtime to WSL ext4 (`/root/...`); the repo stays on the FAT32 stick."*

That is the bad case. `outbox.py` opens the database with:

```python
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA synchronous=FULL")
```

WAL needs a shared-memory `-shm` file and POSIX advisory locking. drvfs over
FAT32 provides neither reliably. The failure is not always loud: SQLite may
silently stay in `delete` journal mode, or throw `disk I/O error` /
`database is locked` under the relay thread's concurrent access — which is exactly
the durability property the outbox exists to provide.

**Fix — set `OUTBOX_DB` onto ext4** (already in §5):

```bash
mkdir -p /root/orbit-state
export OUTBOX_DB=/root/orbit-state/outbox.db
```

**Verify WAL actually engaged** after the orchestrator starts:

```bash
sqlite3 /root/orbit-state/outbox.db 'PRAGMA journal_mode;'    # must print: wal
ls /root/orbit-state/                                        # expect outbox.db, -wal, -shm
```

If it prints `delete`, the database is not where you think it is, or the
filesystem rejected WAL. Do not run exp5 in that state — crash-recovery and
exactly-once results from a non-WAL outbox are not trustworthy.

**This is now enforced in code.** `Outbox.__init__` calls `_assert_wal()`, which
reads back `PRAGMA journal_mode` and raises if it is not `wal`, naming `OUTBOX_DB`
and the fix in the error text. The orchestrator will not start against a non-WAL
outbox, so the silent-fallback case cannot reach a measurement run. Covered by
`tests/test_outbox_relay.py` [7], which forces `journal_mode=DELETE` and asserts
the guard fires.

## B. The contract address, and what caches it

**Where it is configured:** nowhere, explicitly. It is *derived* from the truffle
build artifact `blockchain/setup/ethereum/build/contracts/IoTDataRegistry.json`,
which truffle rewrites on every `migrate`.

**Two consumers, and they disagree:**

| Consumer | Selection | Line |
|----------|-----------|------|
| Orchestrator | `list(artifact['networks'].keys())[-1]` — last in file order | `orchestrator.py:81` |
| exp3 gas | `max(j["networks"], key=int)` — highest numeric network id | `exp3_gas_real.py:97` |

These agree only by luck. Ganache assigns a **timestamp-based network id** when
none is pinned, so each fresh Ganache adds a new key. The artifact currently holds
**18 network entries**, all stale but one — old addresses are never pruned.

**What caches the old one:** the artifact itself. Nothing else does — I grepped
`frontend/`, `orchestrator-js/` and the ethereum scripts for hardcoded `0x…`
addresses and found none. The orchestrator reads the artifact once at import, so a
redeploy after it has started leaves it holding a dead address for the process
lifetime.

**The dangerous part:** the orchestrator does **not** check that code exists at the
address it picked. `exp3_gas_real.py:99` does (`get_code(addr) <= 2` → abort); the
orchestrator constructs the contract object regardless and only fails later, at
transaction time, with a confusing revert or "no contract code" error surfacing
inside the *relay worker* rather than the request.

**Recommended sequence, every time Ganache restarts:**

```bash
# 1. pin the network id so the artifact key is stable across restarts
npx ganache --host 127.0.0.1 --port 8545 --chain.chainId 1337 \
            --networkId 1337 --wallet.deterministic &

# 2. clear stale entries so [-1] and max() cannot diverge
cd /mnt/e/Hybrid_BC_System/blockchain/setup/ethereum
python3 - <<'PY'
import json
p='build/contracts/IoTDataRegistry.json'
a=json.load(open(p)); a['networks']={}; json.dump(a,open(p,'w'),indent=2)
print('cleared networks[]')
PY

# 3. redeploy
npx truffle migrate --network development --reset

# 4. verify (the §3 health check), THEN start the orchestrator
```

Order matters: **always restart the orchestrator after a redeploy.**

**Both problems are now fixed in code**, so the sequence above is a convenience
rather than a discipline requirement:

* `orchestrator/contract_registry.py` holds the single selection rule — highest
  numeric network id — used by both the orchestrator and exp3. They cannot
  diverge because there is only one implementation.
* The orchestrator **refuses to start** when the resolved address holds no
  bytecode (`SystemExit`, with the redeploy command in the message). A stale
  artifact now fails at startup instead of surfacing later inside the relay
  worker, after requests have already been acknowledged with 202.
* Covered by `tests/test_outbox_relay.py` [8], including a case where file order
  and highest-id disagree.

Checked against the current artifact: the two old rules happen to agree today —
both select network `1782885038550` — so no existing result is invalidated. The
risk was real but had not yet fired.

### After the run: prove it was one deployment

`consolidate_results.py` cross-checks the contract address recorded by exp1, exp3
and exp5, and **fails the build** if they differ, naming each experiment and its
address. On success it emits a `run_contract_addr` metric, so `RESULTS.json`
carries positive evidence that every chain-dependent number came from one
deployment — rather than merely not contradicting it.

exp1 and exp5 take the address from the orchestrator's `/health`, which now
reports `contract_addr`, `network_id`, `chain_id` and `outbox_db`. exp3 records
the address it resolved directly. Any experiment that produced results without
recording an address is listed in `not_measured` rather than silently skipped.

Manual check before consolidating, if you want one — all printed addresses must
be identical:

```bash
grep -h -o '"contract_addr[a-z]*": "[^"]*"' \
     experiments/results/exp1/exp1_latency_real.json \
     experiments/results/exp3/exp3_gas_real.json \
     experiments/results/exp5/exp5_exactly_once_real.json | sort -u
```

## C. Hardcoded `200` checks vs the new `202`

The orchestrator now returns **202 Accepted** from `/ingest_data`
(`orchestrator.py:419`). `/health`, `/anchor_status` and `/outbox_stats` still
return 200, and an idempotency replay served from cache also returns 200.

Full grep of `experiments/`, `tests/` and `orchestrator/`:

| File | Line | Verdict |
|------|------|---------|
| `exp5_exactly_once_real.py` | 51 | **WAS BROKEN — fixed** |
| `exp1_latency_real.py` | 110 | OK — `not in (200, 202)` |
| `exp1_latency_real.py` | 148 | OK — `/anchor_status`, still 200 |
| `exp1_latency_real.py` | 283 | OK — `/health`, still 200 |
| `exp5_exactly_once_real.py` | 110 (now ~148) | OK — `/health` |
| `tests/test_outbox_relay.py`, `tests/test_twin_storage.py` | — | no HTTP; unaffected |
| `exp1_latency_throughput.py` | 103, 197, 258 | superseded (pre-Phase-2), not canonical |
| `exp4_lifecycle_overhead.py` | 115, 181, 192, 207, 454 | superseded |
| `exp5_exactly_once.py` | 112, 179, 186, 504 | superseded |
| `_quarantine/exp2_privacy_routing.py` | 101, 219 | quarantined |

The superseded and quarantined files are left alone: they do not feed
`RESULTS.json` and `DATA_SOURCES.md` §4 already records them as replaced.

### exp5 had a second, worse break — also fixed

The status code was the visible half. The response body changed too: under async
anchoring, `/ingest_data` no longer contains `ethereum_tx_hash` — it cannot, the
anchor has not been broadcast when the response is written. exp5 built its whole
result from that field:

```python
return {"tx": j.get("ethereum_tx_hash"), ...}      # now always None
```

So even after fixing the status code, every request would have read `tx = None`,
and the DISTINCT case — 40 unique payloads that must produce 40 unique anchors —
would have collapsed to **1 unique anchor**. The duplicate cases would still have
"passed", so the run would have looked half-plausible while the one case that
actually discriminates was silently inverted.

Fixed by resolving each `outbox_id` through `/anchor_status` and taking
`eth_tx_hash` once delivered. exp5 now accepts 200 and 202, and waits for the
anchor before recording it.

**This is the class of thing to watch for on the stack run:** the async change
altered the response *contract*, not just its status code. Any consumer reading
`ethereum_tx_hash` or `block_number` from an ingest response needs the same
treatment. Those two fields no longer exist there.

---

## Unverified / could not determine from the repo

- **`/root/hybrid-fabric`, `/root/fabric-clean`, `/root/orbit-venv` contents.**
  Recorded in `BRINGUP_STATUS.md` but they live outside the repo and outside this
  Windows filesystem, so I could not inspect them. If any is missing, §1's
  fallback applies.
- **Whether port 5001 is still occupied by the foreign service.** It answered
  `404 page not found` during this session, so 5011 is the safer choice, but the
  occupant may be transient. Check before assuming.
- **Ganache invocation last used.** `BRINGUP_STATUS.md` says "Ganache in WSL
  (`node`), chainId 1337, deterministic" but does not record the exact flags. The
  §2 command reconstructs that description; `--networkId 1337` is my addition for
  the reason in §B.
- **Exact `network.sh up` flags.** `BRINGUP_STATUS.md` records the `createChannel`
  and `deployCC` invocations verbatim but not the preceding `up`. The `-ca -s
  couchdb -i 2.5.0 -cai 1.5.5` in §1 is inferred from the recorded container list
  (CAs + CouchDB) and the pinned tags. If `up` rejects a flag, drop to
  `./network.sh up -ca -s couchdb` with the two `IMAGE_TAG` exports already set.
- **`orchestrator/.venv`** is a WSL Python 3.10 venv inside the repo. Whether it is
  still functional after the phase changes is untested — §5 uses `/root/orbit-venv`,
  which is what the last successful run used.
