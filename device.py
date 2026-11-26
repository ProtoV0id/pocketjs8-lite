"""Framebuffer display and evdev keyboard for the Cardputer Zero.

Adapted from the user's PocketLink device adapter, commit
353ed68ba86a64198a68e4603eb7848570b8f4a6. Device support checks the pixel format
before writing. PocketJS8 hardware operation still requires device validation.
"""
import array
import mmap
import os
import re
import select
import struct
import sys

W, H = 320, 170


class Screen:
    def __init__(self, path):
        import fcntl
        resolved = os.path.realpath(path)
        if not re.fullmatch(r"fb\d+", os.path.basename(resolved)):
            raise RuntimeError("Framebuffer must resolve to /dev/fbN")
        self.fd = os.open(resolved, os.O_RDWR)
        try:
            v = bytearray(160)
            fcntl.ioctl(self.fd, 0x4600, v, True)
            x, y, vx, vy, xoff, yoff, bpp, gray = struct.unpack_from("=8I", v)
            red, green, blue = [struct.unpack_from("=3I", v, n) for n in (32, 44, 56)]
            if ((x, y, bpp, gray, xoff, yoff) != (W, H, 16, 0, 0, 0)
                or red[:2] != (11, 5) or green[:2] != (5, 6)
                or blue[:2] != (0, 5) or sys.byteorder != "little"):
                raise RuntimeError("Unsupported display format; expected 320x170 RGB565")
            fixed_format = "@16sLIIIIHHHI"
            fixed = bytearray(struct.calcsize(fixed_format))
            fcntl.ioctl(self.fd, 0x4602, fixed, True)
            fields = struct.unpack(fixed_format, fixed)
            framebuffer_bytes, self.stride = fields[2], fields[9]
            if framebuffer_bytes < self.stride * H or self.stride < W * 2 or vy < H:
                raise RuntimeError("Unsupported framebuffer stride or memory size")
            self.fb = mmap.mmap(self.fd, self.stride * H, mmap.MAP_SHARED,
                                mmap.PROT_WRITE | mmap.PROT_READ)
        except BaseException:
            os.close(self.fd)
            raise

    def show(self, img):
        raw = array.array("H", (((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                                for r, g, b in img.convert("RGB").getdata())).tobytes()
        for y in range(H):
            self.fb[y*self.stride:y*self.stride+W*2] = raw[y*W*2:(y+1)*W*2]

    def close(self):
        self.fb.close()
        os.close(self.fd)


def default_keyboard():
    for p in (os.environ.get("JS8_KEYBOARD"),
              os.environ.get("APPLAUNCH_LINUX_KEYBOARD_DEVICE"),
              os.environ.get("LV_LINUX_KEYBOARD_DEVICE"),
              "/dev/input/cardputer-zero-internal",
              "/dev/input/by-path/platform-3f804000.i2c-event"):
        if p and os.path.exists(p):
            return p
    return "/dev/input/cardputer-zero-internal"


class KeyTranslator:
    """Translate Linux EV_KEY events to UI actions.

    On the stock Zero, the kernel resolves Fn/Sym hold, tap and lock and emits
    layer-specific key codes.  These codes need M5Stack's console keymap, which
    direct evdev readers bypass.  Only apply that map to the built-in keypad;
    the same numeric codes have different meanings on a normal USB keyboard.
    See m5stack-linux-dtoverlays' cardputerzero-v5-overlay.dts and
    tca8418_keypad_m5stack_keymap.map.
    """
    ZERO_SYMBOLS = {
        26: "!", 27: "@", 39: "#", 40: "$", 41: "%", 43: "^",
        51: "&", 52: "*", 53: "(", 94: ")", 55: "~", 69: "`",
        70: "_", 71: "-", 72: "+", 73: "=", 74: "[", 75: "]",
        76: "{", 77: "}", 79: ";", 80: ":", 81: "'", 82: '"',
        83: "<", 85: ">", 86: "\\", 89: "|", 90: ",", 91: ".",
        92: "/", 93: "?",
    }

    def __init__(self, ecodes, cardputer_zero):
        self.E = ecodes
        self.cardputer_zero = cardputer_zero
        self.down = set()

    def feed(self, code, value, mode):
        """Return (key, character, ctrl) for a press/repeat, or None."""
        E = self.E
        if value == 0:
            self.down.discard(code)
            return None
        if value not in (1, 2):
            return None
        # Holding Enter must not select a menu item and then also activate a
        # transmit confirmation. Navigation and editing can still repeat.
        if value == 2 and code in (E.KEY_ENTER, E.KEY_KPENTER, E.KEY_ESC):
            return None
        self.down.add(code)
        shift = bool({E.KEY_LEFTSHIFT, E.KEY_RIGHTSHIFT} & self.down)
        ctrl = bool({E.KEY_LEFTCTRL, E.KEY_RIGHTCTRL} & self.down)
        special = {E.KEY_UP: "UP", E.KEY_DOWN: "DOWN", E.KEY_LEFT: "LEFT",
                   E.KEY_RIGHT: "RIGHT", E.KEY_ENTER: "ENTER",
                   E.KEY_KPENTER: "ENTER", E.KEY_ESC: "ESC",
                   E.KEY_BACKSPACE: "BACKSPACE"}
        if code in special:
            return special[code], None, ctrl or (shift and code in (E.KEY_ENTER, E.KEY_KPENTER))
        if self.cardputer_zero and code in self.ZERO_SYMBOLS:
            char = self.ZERO_SYMBOLS[code]
            if mode in ("menu", "view", "confirm") and char in (";", "."):
                return ("UP" if char == ";" else "DOWN"), None, False
            return ("CHAR", char, False) if not ctrl else None
        if mode in ("menu", "view", "confirm"):
            nav = {E.KEY_F: "UP", E.KEY_X: "DOWN", E.KEY_Z: "LEFT", E.KEY_C: "RIGHT"}
            if code in nav:
                return nav[code], None, False
            if not self.cardputer_zero and code in (E.KEY_SEMICOLON, E.KEY_DOT):
                return ("UP" if code == E.KEY_SEMICOLON else "DOWN"), None, False
        char = None
        for c in "abcdefghijklmnopqrstuvwxyz":
            if code == getattr(E, "KEY_" + c.upper()):
                char = c.upper() if shift else c
                break
        digits = "1234567890"
        for c in digits:
            if code == getattr(E, "KEY_" + c):
                char = "!@#$%^&*()"[digits.index(c)] if shift else c
                break
        symbols = {E.KEY_SPACE:(" "," "), E.KEY_MINUS:("-","_"),
                   E.KEY_EQUAL:("=","+"), E.KEY_LEFTBRACE:("[","{"),
                   E.KEY_RIGHTBRACE:("]","}"), E.KEY_BACKSLASH:("\\","|"),
                   E.KEY_SEMICOLON:(";",":"), E.KEY_APOSTROPHE:("'",'"'),
                   E.KEY_GRAVE:("`","~"), E.KEY_COMMA:(",","<"),
                   E.KEY_DOT:(".",">"), E.KEY_SLASH:("/","?")}
        if code in symbols:
            char = symbols[code][int(shift)]
        return ("CHAR", char, False) if char and not ctrl else None


def run_device(ui, framebuffer, keyboard):
    try:
        import evdev
    except ImportError as exc:
        raise RuntimeError("Install python3-evdev") from exc
    from evdev import ecodes as E
    screen, kb = Screen(framebuffer), None
    try:
        kb = evdev.InputDevice(keyboard)
        kb.grab()
        translator = KeyTranslator(E, "tca8418" in kb.name.lower())
        while ui.mode != "quit":
            ui.poll()
            frame = ui.draw()
            # Radio activity may update asynchronously, but an unchanged frame
            # does not need another full RGB565 conversion and SPI write.
            payload = frame.tobytes()
            if payload != getattr(screen, "_last_payload", None):
                screen.show(frame)
                screen._last_payload = payload
            ready, _, _ = select.select([kb.fd], [], [], 0.15)
            if not ready:
                continue
            for event in kb.read():
                if event.type != E.EV_KEY:
                    continue
                action = translator.feed(event.code, event.value, ui.mode)
                if action:
                    key, char, ctrl = action
                    ui.input(key, char, ctrl=ctrl)
    finally:
        if kb:
            try:
                kb.ungrab()
            except OSError:
                pass
            kb.close()
        screen.close()

