"""Smoke test against the pinned upstream viewer's real synthetic SSE stream."""
import argparse
import socket
import subprocess
import time

from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from field import Field

parser=argparse.ArgumentParser()
parser.add_argument("viewer")
args=parser.parse_args()
with socket.socket() as sock:
    sock.bind(("127.0.0.1",0))
    port=sock.getsockname()[1]
upstream=subprocess.Popen([args.viewer,"--port",str(port),"--tick-ms","40"])
field=Field(port)
try:
    field.enable(True)
    end=time.monotonic()+15
    while time.monotonic()<end:
        if upstream.poll() is not None:
            raise RuntimeError("Upstream viewer exited")
        snapshot=field.status()
        if snapshot["mode"]=="Synthetic" and any(snapshot["history"]):
            break
        time.sleep(.1)
    else:
        raise AssertionError("No upstream synthetic event counts")
    assert snapshot["presence_at"] is None
    upstream.terminate()
    upstream.wait(timeout=3)
    end=time.monotonic()+12
    while time.monotonic()<end and field.status()["mode"]!="Disconnected":
        time.sleep(.1)
    assert field.status()["mode"]=="Disconnected"
    print("PASS: upstream synthetic frames, source labeling and disconnect")
finally:
    field.enable(False)
    if upstream.poll() is None:
        upstream.terminate()
        upstream.wait(timeout=3)
