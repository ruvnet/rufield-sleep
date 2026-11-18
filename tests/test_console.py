import datetime as dt
import json
import os
import pty
import select
import threading
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app import handler
from field import Field, classify
from habits import Diary, suggestion
from speaker import SerialLink, Speaker


class DiaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Diary(Path(self.tmp.name)/"test.db")

    def log(self,day,bedtime,minutes=10,profile=1):
        self.store.update("night",dict(profile=profile,date=day,bedtime=bedtime,minutes=minutes,comfort=5))

    def test_midnight_personalization_is_separate_and_reversible(self):
        other = self.store.update("new",dict(name="Other"))
        for day,t in zip(("2024-01-01","2024-01-02","2024-01-03"),("23:55","00:05","00:10")):
            self.log(day,t)
        self.log("2024-01-03","00:10",minutes=15)
        state = self.store.state(1)
        self.assertEqual(len(state["nights"]),3)
        self.assertEqual(state["suggestion"]["bedtime"],"00:05")
        self.assertEqual(state["suggestion"]["minutes"],10)
        self.assertEqual(state["profile"]["bedtime"],"22:30")
        self.assertEqual(self.store.state(other)["nights"],[])
        self.store.update("forget",dict(profile=1))
        self.assertIsNone(self.store.state(1)["suggestion"])

    def test_uncertain_routine_and_silence(self):
        for i,t in enumerate(("03:00","11:00","19:00"),1):
            self.log("2024-01-0"+str(i),t)
        self.assertIsNone(self.store.state(1)["suggestion"])
        self.store.update("routine",dict(profile=1,bedtime="00:10",minutes=0,level=1))
        self.assertEqual(self.store.state(1)["profile"]["minutes"],0)

    def test_invalid_night_not_committed(self):
        with self.assertRaises(ValueError):
            self.log("2024-01-01","25:00")
        self.assertFalse(self.store.state(1)["nights"])


def serve(test, cls):
    server=ThreadingHTTPServer(("127.0.0.1",0),cls)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server.server_port


class IntegrationTest(unittest.TestCase):
    def test_viewer_http_sse_provenance_and_minimized_data(self):
        class Viewer(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                source=dict(source="live",synthetic=False,trust_mode="production",banner={"state":"live"})
                frame=dict(verified_count=2,frame=dict(events=[{"private":"omit"}],inferences=[
                    {"label":"person_present","confidence":.98},{"label":"bed_exit","confidence":.88}]))
                source_request=self.path=="/api/source"
                payload=json.dumps(source) if source_request else "event: frame\ndata: "+json.dumps(frame)+"\n\n"
                self.send_response(200)
                self.send_header("Content-Type","application/json" if source_request else "text/event-stream")
                self.end_headers();self.wfile.write(payload.encode())
        field=Field(serve(self,Viewer));field.enable(True);self.addCleanup(field.enable,False)
        end=time.monotonic()+4
        while field.status()["mode"]!="Live" and time.monotonic()<end: time.sleep(.02)
        s=field.status()
        self.assertEqual(s["count"],2);self.assertTrue(s["presence_at"]);self.assertGreater(s["exit_at"],0)
        self.assertNotIn("private",json.dumps(s))
        field.enable(False);self.assertEqual(field.status()["mode"],"Disconnected")
        field.ingest("Live",{"verified_count":2,"frame":{"events":[]}},1)
        self.assertIsNone(field.status()["presence_at"])

    def test_trust_modes_and_stale_frames(self):
        s=dict(source="live",synthetic=False,banner={"state":"live"},trust_mode="captured_replay")
        self.assertEqual(classify(s),"Replay")
        self.assertEqual(classify(dict(s,trust_mode="unknown")),"Disconnected")
        f=Field();f.enabled=True
        f.ingest("Replay",dict(verified_count=1,frame=dict(events=[],inferences=[dict(label="person_present",confidence=1)])),0)
        self.assertIsNone(f.status()["presence_at"])
        f.seen-=9
        self.assertEqual(f.status()["mode"],"Disconnected")
        f.ingest("Synthetic",{"events":[{}]},0)
        self.assertEqual(f.status()["mode"],"Synthetic")
        self.assertFalse(Speaker(None,f).available_field())

    def test_serial_handshake_play_and_stop_on_bed_exit(self):
        master,slave=pty.openpty()
        self.addCleanup(os.close,master);self.addCleanup(os.close,slave)
        heard=[];done=threading.Event()
        def board():
            buf=b""
            while not done.is_set():
                if not select.select([master],[],[],.1)[0]: continue
                buf+=os.read(master,128)
                while b"\n" in buf:
                    line,buf=buf.split(b"\n",1);cmd=line.strip().decode()
                    heard.append(cmd)
                    result={"HELLO":"RFS1","PLAY 2":"PLAYING","KEEP":"ALIVE","STOP":"STOPPED"}.get(cmd,"IDLE")
                    os.write(master,(result+"\n").encode())
        thread=threading.Thread(target=board,daemon=True);thread.start()
        self.addCleanup(thread.join,1);self.addCleanup(done.set)
        f=Field();f.enabled=True
        speaker=Speaker(os.ttyname(slave),f);speaker.connect();self.addCleanup(speaker.disconnect)
        p=dict(id=1,minutes=1,level=2)
        with self.assertRaises(ValueError): speaker.start(p,True)
        with self.assertRaises(ValueError): speaker.start(dict(p,minutes=0),False)
        f.ingest("Live",dict(verified_count=1,frame=dict(events=[])),0)
        speaker.start(p,True)
        with self.assertRaises(ValueError):speaker.start(p,True)
        time.sleep(.9)
        f.ingest("Live",dict(verified_count=1,frame=dict(events=[],inferences=[dict(label="bed_exit",confidence=.9)])),0)
        end=time.monotonic()+2
        while speaker.status()["remaining"] and time.monotonic()<end:time.sleep(.03)
        self.assertEqual(speaker.status()["remaining"],0)
        self.assertIn("KEEP",heard);self.assertEqual(heard[-1],"STOP")

    def test_http_origin_and_profile_roundtrip(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        f=Field();port=serve(self,handler(Diary(Path(tmp.name)/"test.db"),f,Speaker(None,f)))
        url=f"http://127.0.0.1:{port}/api/"
        def post(origin):
            req=urllib.request.Request(url+"new",headers={"X-RuField-Console":"1","Content-Type":"application/json","Origin":origin},data=b'{"name":"Second"}')
            return json.load(urllib.request.urlopen(req))
        with self.assertRaises(urllib.error.HTTPError) as e:post("https://other.example")
        self.assertEqual(e.exception.code,403)
        pid=post(url.split("/api")[0])["profile"]
        self.assertEqual(json.load(urllib.request.urlopen(url+"state?profile="+str(pid)))["profile"]["name"],"Second")
