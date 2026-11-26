# PocketJS8 Lite v0.3.0 — Cardputer Zero / DigiRig Mobile / (tr)uSDX

**A dedicated standalone JS8 terminal.** No desktop JS8Call, Dire Wolf,
second computer, or Internet is required **after initial setup**. The app
runs on the Raspberry Pi-powered M5Stack Cardputer Zero and uses the attached
DigiRig Mobile as its USB audio device and RTS PTT serial interface.

## What is delivered

- **Native real JS8 physical-layer modem bridge:** C++20 source in
  `native/modem.cpp`. Uses an actual, third-party JS8 encoder, modulator,
  and decoder (see upstream below), **not** a fake decode stream.
- **Receive mode:** captures 12 kHz mono 16-bit audio with ALSA `arecord`,
  feeds the native modem continuously, decodes only 15-second JS8 Normal
  periods in a dedicated thread, and logs decoded human-readable frames.
- **Transmit mode:** packs and modulates up to four JS8 Normal frames for a
  short message, starts transmission in a UTC 15-second interval, keys the
  DigiRig using serial RTS, plays through ALSA `aplay`, and releases RTS in
  `finally` on success/cancellation/error.
- **Small-screen native UI:** uses the Zero's 320×170 framebuffer and built-in
  evdev keyboard, with editable station settings, message history, compose,
  frame preview, real hardware selection and explicit transmit unlock.
- **Separate APPLaunch entry:** `PocketJS8 Lite`. Does not modify PocketLink or
  the earlier `PocketJS8` package.

## IMPORTANT: actual hardware operation has not been validated yet

This is a **software beta**, not a verified working radio station. The full
modem needs to be built **on the Zero** and its accuracy/CPU performance tested
with live signals. Host checks, mock modem checks and UI simulations don't
prove DigiRig access or RF interoperability. The third-party modem is young.

The native module is **not included as an ARM binary**. The `.deb` installs
app/source and the one-time build script. The upstream dependency requires
an Internet connection *during first build*, but the finished native modem
needs none during operation.

For step-by-step Cardputer installation from the checked-in `.deb` installer,
see **[INSTALL.md](INSTALL.md)**. The installer is committed at
[`dist/cardputer-js8-lite_0.3.0_all.deb`](dist/cardputer-js8-lite_0.3.0_all.deb);
no GitHub Release page is required.

## First-time installation (Pi Zero / Cardputer Zero)

The instructions target Debian/APPLaunch. On the Zero via SSH:

```sh
# Download the installer from this repository or copy it to the Zero first.
sudo apt update
sudo apt install ./cardputer-js8-lite_0.3.0_all.deb

# Prepare for the first native engine build (Internet needed once).
sudo apt install git cmake build-essential

# Build a pinned upstream JS8 library + PocketJS8 native bridge.
/usr/share/APPLaunch/apps/cardputer-js8-lite/build_engine.sh

# Check the resulting binary and hardware (does not key the radio).
~/.local/bin/pocketjs8-lite-modem version
pocketjs8-lite-check
```

**Memory warning:** A Pi Zero 2 W has 512 MiB RAM. Compiling the third-party
modem's large generated source files can exhaust memory. The build uses one
compile job and -O1 for this reason. If Linux kills the compiler, consider
an explicitly configured *temporary* swap file for the build, then remove
it after building. The app never creates swap automatically.

If your Debian installation is **32-bit `armhf`**, the script compiles natively
for `armhf`. A downloaded upstream `aarch64` JS8Call AppImage would not run on
32-bit ARM. Confirm OS architecture with `dpkg --print-architecture`.

## Physical connection

- Cardputer Zero **USB host** -> DigiRig Mobile USB input (an appropriately
  powered USB host adapter/hub may be needed).
- DigiRig Mobile AUDIO connector -> the correct manufacturer's uSDX/truSDX
  **audio and PTT cable** -> radio headphones and microphone/PTT sockets.
- (tr)uSDX separately powered -> suitable HF antenna or a rated dummy load.
- No CAT control; set frequency manually on the radio. For an initial receive
  check, tune USB at **7.078 MHz on 40 m** or **14.078 MHz on 20 m**.

Linux ALSA `snd-usb-audio` and USB serial (often `cp210x`) are standard kernel
modules, not bundled drivers. `pocketjs8-lite-check` lists hardware by index;
the software never assumes which USB device number belongs to DigiRig.

## Cardputer operation

Open **PocketJS8 Lite** from the APPLaunch wheel.

1. **Station / DigiRig**: set *callsign*, *Maidenhead grid*, *RX audio*,
   *TX audio*, and *PTT serial port*. Select devices from the real ALSA/USB
   lists; the app leaves choices empty rather than guessing.
2. **Start listening**. If configured and the native modem is installed,
   receive-only will auto-start when the app opens. Allow at least one full
   15-second period before expecting decoded frames.
3. **Live messages** shows frames decoded on this Zero, with signal reports,
   audio offsets, and UTC timestamps. The last 100 frames are displayed.
   Transmissions spanning multiple frames appear as separate fragments in
   this release; full message reassembly is not implemented.
4. **Compose short message** (max 48 characters). Review the exact text and
   frame count. Up to four frames are accepted; anything larger is refused.
5. Before any on-air test: verify clock accuracy, cabling, radio output level,
   legal operating frequency, correct antenna/dummy load, and a valid amateur
   radio license. **TX is locked every session**. Select **Transmit controls**,
   deliberately unlock, then review and confirm the message. Unlock is consumed
   after submission. Use the HALT menu if needed.

PocketJS8 Lite never auto-beacons, relays, resends, or changes the radio band.
It has no CAT, automatic replies, map, spotting network, or waterfall.

## Keyboard

- `F` / `X` or the Zero's `Fn+F/X` arrows: scroll
- `Enter`: select or save edited text
- `Esc`: back / cancel
- In a text field, use `Fn+Z/C` arrows to move cursor; Backspace erases

## Safety and limitations

- **Only JS8 Normal (15-second slots)** is decoded/transmitted for this beta.
  Other speeds are intentionally disabled to reduce CPU overhead.
- A **normal USB audio input device** and a **real RS232-style RTS PTT line**
  are necessary; no dummy or simulated transmissions are passed off as RF.
- **The shell's UTC clock must be correct.** With no network, sync before
  leaving coverage or use a reliable hardware RTC/GPS solution. The UI reports
  NTP state when the system offers it but cannot guarantee actual drift.
- **CM108 USB audio / CP210x serial** normally use the Linux kernel drivers.
  No special DigiRig driver or Dire Wolf is bundled.
- Sound capture and playback are half-duplex: receiver capture stops while
  sending and restarts afterward.
- The serial device may assert RTS momentarily during open on some drivers;
  a **dummy-load PTT test** is required before RF use. Reversing or mismatching
  cables can cause unintended PTT or faulty audio.
- TX audio gain defaults to 0.125 of internal modem level. Measure output and
  adjust hardware settings before on-air operation. RF power and ALC are not
  controlled by this app.
- Linux sound-card resampling, audio latency, actual slot alignment, signal
  decoding quality and TX/receiving interoperability require on-device testing.
- Disk writes remain local in `~/.local/share/pocketjs8-lite/` with file mode
  0600 when possible. This is not an encrypted vault.
- `audio device`, `PTT`, and settings may change with USB reconnection; verify
  `pocketjs8-lite-check` output rather than assuming device indices.

## Architecture

```
M5Stack Cardputer Zero, local Linux
  PocketJS8 Lite (Python/Pillow/evdev, framebuffer)
            | 
        radio.py
         |                         
    arecord (ALSA USB capture) => pocketjs8-lite-modem rx (native C++20)
    pocketjs8-lite-modem frames/tx => aplay (ALSA USB output)
                                     + DigiRig serial RTS PTT
            |
      DigiRig Mobile -> (tr)uSDX -> HF antenna
```

## Source and upstream pin

Pinned dependency: [jfrancis42/gfsk8-modem-clean](https://github.com/jfrancis42/gfsk8-modem-clean)
commit `bd6457e0bd4c3a10e74d1c1aaa5e86f67565168a` (GPL-3.0).
The build script fetches exactly that revision and runs upstream tests before
linking this project's `native/modem.cpp`.

All project source is shipped in the ZIP and Debian package. Source files are
GPL-3.0-or-later; the linked upstream library is GPL-3.0. The developer's
modem library provides physical-layer JS8 and basic frame parsing but is not
an official JS8Call release. Treat compatibility claims as unverified until a
live interoperability test.

## Local development

```sh
python3 -m unittest discover -s tests -v
python3 pocketjs8_lite.py --preview preview/home.png
python3 build_package.py
```

Tests use mocks for native modem/audio/PTT and do not claim an RF round trip.
