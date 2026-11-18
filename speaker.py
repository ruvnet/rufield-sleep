"""Serial control for one locally attached speaker. The board enforces its own lease."""
import os
import select
import threading
import time

class SerialLink:
    def __init__(self, path):
        import termios
        import tty
        self.fd = os.open(path,os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        try:
            tty.setraw(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[4] = attrs[5] = termios.B115200
            termios.tcsetattr(self.fd,termios.TCSANOW,attrs)
            # Some USB bridges reset the board on opening the port.
            time.sleep(1.5)
            self.exchange("HELLO","RFS1")
        except Exception:
            self.close()
            raise

    def exchange(self, command, reply):
        import termios
        termios.tcflush(self.fd,termios.TCIFLUSH)
        payload=(command+"\n").encode()
        if os.write(self.fd,payload) != len(payload):
            raise OSError("Incomplete serial command")
        buf=b""
        end=time.monotonic()+.85
        while len(buf)<512 and time.monotonic()<end:
            readable,_,_=select.select([self.fd],[],[],max(0,end-time.monotonic()))
            if readable:
                data=os.read(self.fd,128)
                if not data:
                    break
                buf+=data
                if reply.encode() in [s.strip() for s in buf.split(b"\n")[:-1]]:
                    return
        raise OSError("Speaker acknowledgement missing")

    def close(self):
        os.close(self.fd)


class Speaker:
    def __init__(self, path, field, factory=SerialLink):
        self.path,self.field,self.factory=path,field,factory
        self.lock=threading.RLock()
        self.link=None
        self.job=None
        self.message="Speaker disconnected"

    def status(self):
        with self.lock:
            job=self.job
            return dict(configured=bool(self.path),connected=bool(self.link), message=self.message,
                        remaining=max(0,round(job["end"]-time.monotonic())) if job else 0,
                        profile=job["profile"] if job else None)

    def connect(self):
        with self.lock:
            if self.link:
                return
            if not self.path:
                raise ValueError("Start the console with --speaker and the board's USB serial path.")
            self.link=self.factory(self.path)
            self.message="Speaker ready"

    def _drop(self):
        self.job=None
        if self.link:
            self.link.close()
        self.link=None
        self.message="Link lost. Board lease expires within three seconds."

    def stop(self, reason="Stopped"):
        with self.lock:
            self.job=None
            if self.link:
                try:
                    self.link.exchange("STOP","STOPPED")
                except OSError:
                    self._drop()
                    return
            self.message=reason

    def available_field(self):
        field=self.field.status()
        return field["mode"]=="Live" and field["count"]>0

    def start(self, profile, live_guard):
        with self.lock:
            if profile["minutes"] == 0:
                raise ValueError("Sound is off for this profile.")
            if self.job:
                raise ValueError("Stop the active session before starting another.")
            if not self.link:
                raise ValueError("Connect the USB speaker first.")
            if live_guard and not self.available_field():
                raise ValueError("Waiting for verified observations from the live sensor.")
            try:
                self.link.exchange(f'PLAY {profile["level"]}',"PLAYING")
            except OSError:
                self._drop()
                raise
            job=dict(profile=profile["id"],started=time.monotonic(),end=time.monotonic()+profile["minutes"]*60,guard=live_guard)
            self.job=job
            self.message="Wind down playing"
            threading.Thread(target=self._maintain,args=(job,),daemon=True).start()

    def _maintain(self,job):
        while True:
            time.sleep(.7)
            with self.lock:
                if self.job is not job:
                    return
                if job["guard"] and self.field.status().get("exit_at", 0) > job["started"]:
                    self.stop("Stopped after a RuField bed exit observation")
                    return
                if time.monotonic()>=job["end"] or (job["guard"] and not self.available_field()):
                    self.stop("Timer ended or room sensor unavailable")
                    return
                try:
                    self.link.exchange("KEEP","ALIVE")
                except OSError:
                    self._drop()
                    return

    def disconnect(self):
        with self.lock:
            self.stop()
            if self.link:
                self.link.close()
                self.link=None
            self.message="Speaker disconnected"
