"""Read a local RuField viewer's public SSE projection. Retain only aggregate counts."""
import http.client
import json
import threading
import time


def classify(source):
    if source.get("synthetic") is True and source.get("source") == "synthetic":
        return "Synthetic"
    if source.get("source") != "live" or source.get("synthetic") is not False:
        return "Disconnected"
    if source.get("banner", {}).get("state") != "live":
        return "Disconnected"
    return {"production":"Live", "captured_replay":"Replay"}.get(source.get("trust_mode"),"Disconnected")


class Field:
    def __init__(self, port=8088):
        self.port = port
        self.lock = threading.Lock()
        self.generation = 0
        self.enabled = False
        self.reset()

    def reset(self):
        self.mode, self.seen, self.count = "Disconnected", 0, 0
        self.history = []
        self.presence_at = None
        self.exit_at = 0.0

    def enable(self, on):
        with self.lock:
            self.generation += 1
            generation = self.generation
            self.enabled = on
            self.reset()
        if on:
            threading.Thread(target=self.watch, args=(generation,), daemon=True).start()

    def active(self, generation):
        with self.lock:
            return self.enabled and self.generation == generation

    def ingest(self, mode, data, generation):
        if mode == "Synthetic":
            events = data["events"]
            if not isinstance(events, list):
                raise ValueError("Invalid frame")
            count = len(events)
        else:
            count = data["verified_count"]
            if type(count) is not int or not 0 <= count <= 100000:
                raise ValueError("Invalid verified count")
            if not isinstance(data["frame"]["events"], list):
                raise ValueError("Invalid live projection")
        inferences = [] if mode != "Live" or count == 0 else data["frame"].get("inferences", [])
        cues = {i["label"] for i in inferences if isinstance(i, dict) and
                i.get("label") in ("person_present", "bed_exit") and
                type(i.get("confidence")) in (int, float) and .8 <= i["confidence"] <= 1}
        with self.lock:
            if self.generation != generation or not self.enabled:
                return
            self.mode, self.seen, self.count = mode, time.monotonic(), count
            if "person_present" in cues:
                self.presence_at = time.time()
            if "bed_exit" in cues:
                self.exit_at = time.monotonic()
            self.history = (self.history + [count])[-36:]

    def status(self):
        with self.lock:
            fresh = self.enabled and self.seen > 0 and time.monotonic()-self.seen < 8
            return dict(enabled=self.enabled,mode=self.mode if fresh else "Disconnected",
                        presence_at=self.presence_at if fresh and self.mode=="Live" and self.presence_at and time.time()-self.presence_at < 120 else None,
                        exit_at=self.exit_at if fresh and self.mode=="Live" else 0,
                        count=self.count if fresh else 0,history=self.history[:] if fresh else [])

    def watch(self, generation):
        while self.active(generation):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
            try:
                conn.request("GET","/api/source")
                response = conn.getresponse()
                if response.status != 200:
                    raise ValueError("Source unavailable")
                mode = classify(json.loads(response.read(16385)))
                if mode == "Disconnected":
                    raise ValueError("Viewer disconnected")
                conn.close()
                conn.request("GET","/events",headers={"Accept":"text/event-stream"})
                response = conn.getresponse()
                if response.status != 200 or "text/event-stream" not in response.getheader("Content-Type",""):
                    raise ValueError("Invalid stream")
                event, parts, size = "", [], 0
                until = time.monotonic()+10
                while self.active(generation) and time.monotonic()<until:
                    raw = response.readline(131073)
                    if not raw or len(raw)>131072:
                        break
                    line = raw.decode().rstrip("\r\n")
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        size += len(line)
                        if size > 131072:
                            break
                        parts.append(line[5:].lstrip())
                    elif not line:
                        if event=="frame" and parts:
                            self.ingest(mode,json.loads("\n".join(parts)),generation)
                        event, parts, size = "", [], 0
            except (OSError,ValueError,TypeError,KeyError,AttributeError,http.client.HTTPException):
                with self.lock:
                    if self.generation == generation:
                        self.reset()
            finally:
                conn.close()
            time.sleep(1)
