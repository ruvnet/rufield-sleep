"""Run with python3 app.py and visit the loopback URL printed at startup."""
import argparse
import json
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from field import Field
from habits import Diary
from speaker import Speaker

WEB=Path(__file__).resolve().parent/"web"
ASSETS={"/":("index.html","text/html"),"/app.js":("app.js","text/javascript"),"/style.css":("style.css","text/css")}

def handler(diary,field,speaker):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, typ="application/json"):
            buf=json.dumps(data).encode() if typ=="application/json" else data
            self.send_response(status)
            self.send_header("Content-Type",typ+"; charset=utf-8")
            self.send_header("Content-Length",str(len(buf)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(buf)

        def allowed(self,write=False):
            host=self.headers.get("Host","")
            port=self.server.server_address[1]
            ok=host in (f"127.0.0.1:{port}",f"localhost:{port}")
            if write:
                ok=ok and self.headers.get("Origin","http://"+host)=="http://"+host
                ok=ok and self.headers.get("X-RuField-Console")=="1" and self.headers.get_content_type()=="application/json"
            if not ok:
                self.send(403,{"error":"Use the local console address."})
            return ok

        def do_GET(self):
            if not self.allowed():
                return
            url=urlsplit(self.path)
            if url.path in ASSETS:
                name,typ=ASSETS[url.path]
                return self.send(200,(WEB/name).read_bytes(),typ)
            if url.path=="/api/state":
                try:
                    pid=int(parse_qs(url.query).get("profile",["1"])[0])
                    return self.send(200,{**diary.state(pid),"sensor":field.status(),"speaker":speaker.status()})
                except ValueError as err:
                    return self.send(400,{"error":str(err)})
            self.send(404,{"error":"Unknown route."})

        def do_POST(self):
            if not self.allowed(True):
                return
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=4096:
                    return self.send(413,{"error":"Invalid request size."})
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):
                    raise ValueError("Expected a JSON object.")
                action=self.path.removeprefix("/api/")
                if self.path in ("/api/new","/api/routine","/api/night","/api/forget"):
                    return self.send(200,{"profile":diary.update(action,body)})
                if action=="sensor":
                    if type(body["enabled"]) is not bool:
                        raise ValueError("Expected a sensor switch.")
                    field.enable(body["enabled"])
                elif action=="connect":
                    speaker.connect()
                elif action=="disconnect":
                    speaker.disconnect()
                elif action=="start":
                    if type(body["guard"]) is not bool:
                        raise ValueError("Expected a sensor guard switch.")
                    speaker.start(diary.state(body["profile"])["profile"],body["guard"])
                elif action=="stop":
                    speaker.stop()
                else:
                    return self.send(404,{"error":"Unknown action."})
                self.send(200,{"ok":True})
            except (KeyError,TypeError,ValueError,UnicodeError) as err:
                self.send(400,{"error":str(err)})
            except sqlite3.IntegrityError:
                self.send(409,{"error":"Choose a different profile name."})
            except OSError:
                self.send(503,{"error":"USB speaker unavailable. Check the port, firmware and cable."})
    return Handler

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8787)
    parser.add_argument("--viewer-port",type=int,default=8088)
    parser.add_argument("--speaker",help="POSIX USB serial device for the ESP32 speaker")
    parser.add_argument("--db",type=Path,default=Path.home()/".local/share/rufield-sleep/diary.db")
    args=parser.parse_args()
    os.umask(0o077)
    args.db.parent.mkdir(parents=True,exist_ok=True)
    field=Field(args.viewer_port)
    speaker=Speaker(args.speaker,field)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler(Diary(args.db),field,speaker))
    print(f"RuField Sleep   http://127.0.0.1:{server.server_port}",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        field.enable(False)
        speaker.disconnect()
        server.server_close()

if __name__=="__main__":
    main()
