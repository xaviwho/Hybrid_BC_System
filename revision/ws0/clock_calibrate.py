"""Compare the WSL clocks with the Windows host clock over DURATION seconds.

Run inside WSL. The host reference is [DateTime]::UtcNow through powershell.exe
interop, bracketed by monotonic reads; half the bracket width is the timing
uncertainty at each end. Every CLOCK_REALTIME step larger than 50 ms relative to
CLOCK_MONOTONIC is logged.

The host clock is only a reference if it is itself disciplined (w32time running
and synced); record `w32tm /query /status` next to the output.

Usage: python clock_calibrate.py [DURATION_S] [OUT_JSON]
"""
import json
import subprocess
import sys
import time

PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
OUT = sys.argv[2] if len(sys.argv) > 2 else None


def host_now():
    a = time.monotonic()
    ticks = subprocess.run([PS, "-NoProfile", "-Command", "[DateTime]::UtcNow.Ticks"],
                           capture_output=True, text=True, check=True,
                           cwd="/mnt/c").stdout.strip()  # interop needs a Windows cwd
    b = time.monotonic()
    # .NET ticks are 100 ns since 0001-01-01; only differences are used.
    return int(ticks) / 1e7, (a + b) / 2, b - a


h0, m0, w0 = host_now()
r0 = time.time()
steps = []
prev = time.time() - time.monotonic()
end = time.monotonic() + DUR
while time.monotonic() < end:
    time.sleep(0.2)
    off = time.time() - time.monotonic()
    if abs(off - prev) > 0.05:
        steps.append([round(time.monotonic() - m0, 1), round(off - prev, 3)])
    prev = off
h1, m1, w1 = host_now()
r1 = time.time()

dh = h1 - h0
res = {
    "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "duration_host_s": round(dh, 3),
    "monotonic_rate_vs_host": round((m1 - m0) / dh, 5),
    "realtime_rate_vs_host": round((r1 - r0) / dh, 5),
    "rate_uncertainty": round((w0 + w1) / 2 / dh, 5),
    "realtime_steps_s": steps,
}
print(json.dumps(res, indent=1))
if OUT:
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
