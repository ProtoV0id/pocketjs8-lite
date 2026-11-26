"""PocketJS8 Lite audio/radio controller; receive-only until explicitly armed.
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations
import datetime as dt
import fcntl
import glob
import json
import os
from pathlib import Path
import queue
import re
import struct
import subprocess
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pocketjs8-lite"
CONFIG = STATE / "config.json"
LOG = STATE / "rx.jsonl"
NATIVE = Path.home() / ".local/bin/pocketjs8-lite-modem"
PERIOD = 15
MAX_FRAMES = 4
CALL_RE = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{1,4}(?:/P|/M|/QRP)?$")
GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2})?$")
AUDIO_RE = re.compile(r"^plughw:[0-9]+,[0-9]+$")
SERIAL_RE = re.compile(r"^/dev/(ttyUSB[0-9]+|ttyACM[0-9]+|serial/by-id/[A-Za-z0-9_.:-]+)$")


def setup_dir():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(STATE, 0o700)
    except OSError:
        pass


def default_config():
    return {"call": "", "grid": "", "rx_audio": "", "tx_audio": "", "ptt_port": "", "draft": ""}


def load_config():
    result = default_config()
    try:
        with CONFIG.open(encoding="utf8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            result.update({k: str(data[k]) for k in result if k in data and isinstance(data[k], str)})
    except (FileNotFoundError, ValueError, OSError):
        pass
    return result


def save_config(cfg):
    setup_dir()
    safe = {k: str(cfg.get(k, "")) for k in default_config()}
    pending = CONFIG.with_suffix(".tmp")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as fh:
            json.dump(safe, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        pending.replace(CONFIG)
        os.chmod(CONFIG, 0o600)
    finally:
        pending.unlink(missing_ok=True)


def audio_devices(command="arecord"):
    """List playback/capture hardware by ALSA card and device number."""
    if command not in ("arecord", "aplay"):
        raise ValueError("unsupported command")
    try:
        cp = subprocess.run([command, "-l"], text=True, capture_output=True, timeout=4, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    matches = []
    for line in cp.stdout.splitlines():
        found = re.search(r"card\s+(\d+):\s+(.+?),\s+device\s+(\d+):\s+(.+)", line, re.I)
        if found:
            num, label, device, detail = found.groups()
            matches.append({"device": f"plughw:{num},{device}", "label": f"card {num}: {label}, device {device}: {detail}"})
    return matches


def serial_devices():
    # Preserve stable /dev/serial/by-id names when available.
    by_id = sorted(glob.glob("/dev/serial/by-id/*"))
    direct = sorted(glob.glob("/dev/ttyUSB[0-9]*") + glob.glob("/dev/ttyACM[0-9]*"))
    return [p for p in by_id + direct if SERIAL_RE.fullmatch(p)]


def utc_seconds():
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")


def ntp_status():
    try:
        cp = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], text=True,
                            capture_output=True, timeout=2, check=False)
        return cp.stdout.strip() == "yes"
    except (OSError, subprocess.TimeoutExpired):
        return False


def recent_rx(max_items=100):
    try:
        with LOG.open(encoding="utf8") as fh:
            lines = fh.readlines()[-max_items:]
        return [json.loads(x) for x in lines if x.strip()]
    except (OSError, ValueError):
        return []


def append_rx(event):
    setup_dir()
    with LOG.open("a", encoding="utf8") as fh:
        fh.write(json.dumps(event, ensure_ascii=True) + "\n")
    os.chmod(LOG, 0o600)
    if LOG.stat().st_size > 200_000:
        with LOG.open(encoding="utf8") as fh:
            retained = fh.readlines()[-500:]
        with LOG.open("w", encoding="utf8") as fh:
            fh.writelines(retained)
        os.chmod(LOG, 0o600)


class Radio:
    def __init__(self, native=NATIVE):
        self.native = str(native)
        self.cfg = load_config()
        self.events = queue.Queue()
        self.rx_state = "STOPPED"
        self.tx_state = "IDLE"
        self.tx_unlocked = False
        self._ptt_fault = False
        self.rxs = recent_rx()
        self._arecord = None
        self._decoder = None
        self._player = None
        self._ptt_fd = None
        self._tx_cancel = threading.Event()
        self._tx_thread = None
        self._lock = threading.RLock()
        self._rx_serial = 0

    def _event(self, event, **fields):
        self.events.put({"event": event, **fields})

    def configured(self):
        return bool(AUDIO_RE.fullmatch(self.cfg["rx_audio"]))

    def native_installed(self):
        return os.path.isfile(self.native) and os.access(self.native, os.X_OK)

    def start_rx(self):
        with self._lock:
            if self._tx_thread and self._tx_thread.is_alive():
                return False, "Transmit in progress"
            if self._decoder and self._decoder.poll() is None:
                return True, "Already listening"
            if not self.native_installed():
                return False, "Build the native JS8 modem first"
            if not self.configured():
                return False, "Choose DigiRig RX audio"
            self._rx_serial += 1
            generation = self._rx_serial
            capture = None
            try:
                capture = subprocess.Popen(["arecord", "-q", "-D", self.cfg["rx_audio"],
                    "-f", "S16_LE", "-r", "12000", "-c", "1", "-t", "raw"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                decoder = subprocess.Popen([self.native, "rx"],
                    stdin=capture.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=False, bufsize=0)
                capture.stdout.close()
            except OSError as err:
                if capture:
                    capture.terminate()
                    capture.wait(timeout=3)
                return False, str(err)
            self._arecord = capture
            self._decoder = decoder
            self.rx_state = "STARTING"
            threading.Thread(target=self._rx_output, args=(generation,decoder,capture), daemon=True).start()
            return True, "Audio capture started"

    def _rx_output(self, generation, decoder, capture):
        try:
            for raw in decoder.stdout:
                try:
                    evt = json.loads(raw.decode("utf8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                with self._lock:
                    if generation != self._rx_serial:
                        break
                    if evt.get("event") == "ready":
                        self.rx_state = "LISTENING"
                    elif evt.get("event") == "decode":
                        evt["received_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
                        append_rx(evt)
                        self.rxs.append(evt)
                        self.rxs = self.rxs[-100:]
                    self._event("rx_event", data=evt)
        finally:
            if capture.poll() is None:
                capture.terminate()
            if decoder.poll() is None:
                decoder.terminate()
            # Keep diagnostics user-visible rather than pretending to decode.
            with self._lock:
                if generation == self._rx_serial:
                    self.rx_state="STOPPED"
                    self._event("rx_stopped", message="Receiver exited; check capture device and logs")

    def stop_rx(self):
        with self._lock:
            self._rx_serial += 1
            capture, decoder = self._arecord, self._decoder
            self._arecord = self._decoder = None
            self.rx_state = "STOPPED"
        for p in (capture,decoder):
            if p is not None and p.poll() is None:
                p.terminate()
        for p in (capture,decoder):
            if p is not None:
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=2)
                for pipe in (p.stdout, p.stderr, p.stdin):
                    if pipe:
                        pipe.close()

    def review(self, text):
        text = text.strip().upper()
        if not self.native_installed():
            raise RuntimeError("Native modem isn't built. Run build_engine.sh")
        if not CALL_RE.fullmatch(self.cfg["call"].upper()):
            raise RuntimeError("Enter a valid amateur callsign")
        if not GRID_RE.fullmatch(self.cfg["grid"].upper()):
            raise RuntimeError("Enter grid (e.g. DM33)")
        if not (0 < len(text) <= 48) or any(ord(x)<32 or ord(x)>126 for x in text):
            raise RuntimeError("Use 1-48 printable characters")
        cmd=[self.native, "frames", "--call", self.cfg["call"].upper(),
             "--grid", self.cfg["grid"].upper(), "--message", text]
        cp=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
        if cp.returncode != 0:
            raise RuntimeError("JS8 message packing failed: "+cp.stderr.strip()[:120])
        try:
            count=int(json.loads(cp.stdout)["frames"])
        except (ValueError,KeyError,TypeError):
            raise RuntimeError("Modem returned an invalid frame count")
        if count < 1 or count > MAX_FRAMES:
            raise RuntimeError(f"Message needs {count} frames. Limit: {MAX_FRAMES}.")
        return {"message":text,"call":self.cfg["call"].upper(),"grid":self.cfg["grid"].upper(),
                "audio":self.cfg["tx_audio"],"port":self.cfg["ptt_port"],"frames":count}

    def unlock(self):
        with self._lock:
            if self._ptt_fault:
                return False
            self.tx_unlocked=True
            return True

    def lock(self):
        with self._lock:
            self.tx_unlocked=False

    def transmit(self, snapshot):
        with self._lock:
            if self._ptt_fault:
                return False,"PTT dekey failed; restart after checking hardware"
            if not self.tx_unlocked:
                return False,"TX locked; unlock it first"
            if self._tx_thread and self._tx_thread.is_alive():
                return False,"Transmit already in progress"
            if not AUDIO_RE.fullmatch(snapshot.get("audio","")):
                return False,"Choose DigiRig TX audio"
            if not SERIAL_RE.fullmatch(snapshot.get("port","")):
                return False,"Choose DigiRig PTT serial port"
            if (snapshot["audio"] != self.cfg["tx_audio"] or
                snapshot["port"] != self.cfg["ptt_port"] or
                snapshot["call"] != self.cfg["call"].upper() or
                snapshot["grid"] != self.cfg["grid"].upper()):
                return False,"Settings changed; review message again"
            self.tx_unlocked=False # one deliberate send per explicit unlock
            self._tx_cancel.clear()
            self.tx_state="PREPARING"
            self._tx_thread=threading.Thread(target=self._transmit_work,args=(dict(snapshot),),daemon=True)
            self._tx_thread.start()
            return True,"Transmission scheduled"

    def halt(self):
        self._tx_cancel.set()
        with self._lock:
            if self._player and self._player.poll() is None:
                self._player.terminate()
            if self._ptt_fd is not None:
                try:
                    fcntl.ioctl(self._ptt_fd, termios.TIOCMBIC, struct.pack("I",termios.TIOCM_RTS))
                except OSError:
                    self._ptt_fault = True
                    self.tx_unlocked = False
                    self._event("tx_status",status="WARNING: PTT release not confirmed")
        self._event("tx_status", status="HALT REQUESTED")

    def _assert_ptt(self, port):
        if not SERIAL_RE.fullmatch(port):
            raise RuntimeError("PTT port rejected")
        fd=os.open(port,os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            # Clear RTS immediately on opening. Some USB serial drivers may
            # momentarily assert control lines during open: bench-test first.
            fcntl.ioctl(fd,termios.TIOCMBIC,struct.pack("I",termios.TIOCM_RTS))
            if self._tx_cancel.is_set():
                raise RuntimeError("Cancelled")
            fcntl.ioctl(fd,termios.TIOCMBIS,struct.pack("I",termios.TIOCM_RTS))
        except BaseException:
            os.close(fd)
            raise
        with self._lock:
            self._ptt_fd=fd
        return fd

    def _release_ptt(self,fd):
        if fd is not None:
            try:
                fcntl.ioctl(fd,termios.TIOCMBIC,struct.pack("I",termios.TIOCM_RTS))
            except OSError as exc:
                # Never claim successful dekey when a USB serial device vanished.
                self._ptt_fault = True
                self.tx_unlocked = False
                self._event("tx_status",status="WARNING: PTT dekey ioctl failed: " + str(exc))
            finally:
                with self._lock:
                    self._ptt_fd=None
                os.close(fd)

    def _transmit_work(self,snapshot):
        status="COMPLETE"
        try:
            self.stop_rx() # half-duplex: never capture audio while playing TX
            wavs=[]
            for index in range(snapshot["frames"]):
                if self._tx_cancel.is_set():
                    raise RuntimeError("Cancelled")
                cmd=[self.native,"tx","--call",snapshot["call"],"--grid",snapshot["grid"],
                     "--message",snapshot["message"],"--index",str(index)]
                wav=subprocess.run(cmd,capture_output=True,timeout=20)
                if wav.returncode != 0 or len(wav.stdout)<100_000 or len(wav.stdout)%2:
                    raise RuntimeError("Failed to render transmit audio")
                wavs.append(wav.stdout)
            for index,data in enumerate(wavs):
                if self._tx_cancel.is_set():
                    raise RuntimeError("Cancelled")
                # Start ALSA player ahead of slot to avoid launching at UTC edge.
                self.tx_state=f"SLOT {index+1}/{len(wavs)}"
                self._event("tx_status",status=self.tx_state)
                edge=(int(time.time()//PERIOD)+1)*PERIOD
                # If slot is too close, advance to next 15 s interval.
                if edge-time.time()<1.0:
                    edge+=PERIOD
                while time.time()<edge-0.8:
                    if self._tx_cancel.wait(timeout=0.05):
                        raise RuntimeError("Cancelled")
                player=subprocess.Popen(["aplay","-q","-D",snapshot["audio"],"-f","S16_LE",
                    "-r","12000","-c","1","-t","raw"],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
                with self._lock:
                    self._player=player
                if self._tx_cancel.is_set():
                    raise RuntimeError("Cancelled")
                if player.poll() is not None:
                    raise RuntimeError("ALSA player failed before PTT")
                fd=None
                try:
                    while time.time()<edge-0.4:
                        if self._tx_cancel.wait(timeout=0.01):
                            raise RuntimeError("Cancelled")
                    if player.poll() is not None:
                        raise RuntimeError("ALSA player exited before PTT")
                    fd=self._assert_ptt(snapshot["port"])
                    while time.time()<edge:
                        if self._tx_cancel.wait(timeout=0.005):
                            raise RuntimeError("Cancelled")
                    self.tx_state=f"ON AIR {index+1}/{len(wavs)}"
                    self._event("tx_status",status=self.tx_state)
                    try:
                        _,stderr=player.communicate(input=data,timeout=17)
                    except subprocess.TimeoutExpired:
                        player.kill();player.communicate()
                        raise RuntimeError("Audio playback timed out")
                    if player.returncode!=0:
                        raise RuntimeError("ALSA transmit failed: "+stderr.decode("utf8","replace")[:80])
                finally:
                    if player.poll() is None:
                        player.terminate()
                        try: player.wait(timeout=2)
                        except subprocess.TimeoutExpired: player.kill(); player.wait()
                    if fd is not None:
                        self._release_ptt(fd)
                    with self._lock:
                        self._player=None
                if self._tx_cancel.is_set():
                    raise RuntimeError("Cancelled")
            status="AUDIO PLAYED; NO ACKNOWLEDGMENT"
            self._event("tx_status",status=status)
        except Exception as exc:
            status="STOPPED: "+str(exc)
            self._event("tx_status",status=status)
        finally:
            # Preserve explicit warning about release failures in the log/UI.
            self.tx_state=("PTT FAULT - UNVERIFIED" if self._ptt_fault else status)
            self.tx_unlocked=False
            # The native receiver is independent: resume even if TX aborted.
            # Clear the TX thread guard before attempting to restart.
            with self._lock:
                self._tx_thread=None
            ok,msg=self.start_rx()
            if not ok:
                self._event("rx_stopped",message="RX restart: "+msg)

    def save(self):
        save_config(self.cfg)

    def close(self):
        self.halt()
        if self._tx_thread and self._tx_thread.is_alive():
            self._tx_thread.join(timeout=3)
        self.stop_rx()
        self.lock()
