"""Rate of each local clock against NTP (UTC), over DURATION seconds.

Answers AUDIT_WS0 F1's open question: with w32time stopped, is the Windows host
clock a valid reference, and how fast does WSL CLOCK_MONOTONIC (the clock every
v1/v2 duration is measured on) run against UTC?

Each sample queries several NTP servers (SNTP, UDP 123), using the midpoint of
each query as the local read time. Reported per clock: rate = elapsed_clock /
elapsed_UTC, with the NTP round-trip spread as the uncertainty.

Usage: python clock_vs_ntp.py [DURATION_S] [OUT_JSON]
"""
import json
import socket
import statistics
import struct
import subprocess
import sys
import time

SERVERS = ["time.google.com", "time.cloudflare.com", "pool.ntp.org"]
NTP_EPOCH = 2208988800
PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0


def sntp(server):
    """Return (utc_seconds_at_midpoint, monotonic_midpoint, realtime_midpoint, rtt)."""
    pkt = b"\x1b" + 47 * b"\0"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(3)
        m0, r0 = time.monotonic(), time.time()
        s.sendto(pkt, (server, 123))
        data, _ = s.recvfrom(48)
        m1, r1 = time.monotonic(), time.time()
    sec, frac = struct.unpack("!II", data[40:48])     # transmit timestamp
    utc = sec - NTP_EPOCH + frac / 2 ** 32
    return utc, (m0 + m1) / 2, (r0 + r1) / 2, m1 - m0


def host_now():
    a = time.monotonic()
    t = subprocess.run([PS, "-NoProfile", "-Command", "[DateTime]::UtcNow.Ticks"],
                       capture_output=True, text=True, check=True, cwd="/mnt/c").stdout
    b = time.monotonic()
    return int(t) / 1e7, (a + b) / 2, b - a


def sample():
    out = {"ntp": []}
    for srv in SERVERS:
        try:
            out["ntp"].append(dict(zip(("utc", "mono", "real", "rtt"), sntp(srv)), server=srv))
        except OSError as e:
            out.setdefault("errors", []).append(f"{srv}: {e}")
    out["host"] = dict(zip(("host", "mono", "width"), host_now()))
    return out


s0 = sample()
time.sleep(DUR)
s1 = sample()

rates = {"monotonic": [], "realtime": []}
for a in s0["ntp"]:
    b = next((x for x in s1["ntp"] if x["server"] == a["server"]), None)
    if not b:
        continue
    du = b["utc"] - a["utc"]
    rates["monotonic"].append((b["mono"] - a["mono"]) / du)
    rates["realtime"].append((b["real"] - a["real"]) / du)
# host vs UTC: map host reads onto the monotonic timeline, then onto UTC via NTP
if s0["ntp"] and s1["ntp"]:
    a, b = s0["ntp"][0], s1["ntp"][0]
    k = (b["utc"] - a["utc"]) / (b["mono"] - a["mono"])          # utc per mono second
    utc_at = lambda mono: a["utc"] + (mono - a["mono"]) * k      # noqa: E731
    dh = s1["host"]["host"] - s0["host"]["host"]
    du_h = utc_at(s1["host"]["mono"]) - utc_at(s0["host"]["mono"])
    host_rate = dh / du_h
    host_offset_s = s1["host"]["host"] - utc_at(s1["host"]["mono"])
else:
    host_rate = host_offset_s = None

res = {
    "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "duration_s": DUR,
    "servers_answered": [x["server"] for x in s1["ntp"]],
    "errors": s0.get("errors", []) + s1.get("errors", []),
    "wsl_monotonic_rate_vs_utc": round(statistics.fmean(rates["monotonic"]), 5) if rates["monotonic"] else None,
    "wsl_realtime_rate_vs_utc": round(statistics.fmean(rates["realtime"]), 5) if rates["realtime"] else None,
    "windows_host_rate_vs_utc": round(host_rate, 5) if host_rate else None,
    "windows_host_offset_from_utc_s": round(host_offset_s, 3) if host_offset_s is not None else None,
    "ntp_rtt_ms": [round(x["rtt"] * 1000, 1) for x in s0["ntp"] + s1["ntp"]],
    "rate_uncertainty": round(max(x["rtt"] for x in s0["ntp"] + s1["ntp"]) / DUR, 5)
                        if s0["ntp"] and s1["ntp"] else None,
}
print(json.dumps(res, indent=1))
if len(sys.argv) > 2:
    with open(sys.argv[2], "w") as f:
        json.dump(res, f, indent=1)
