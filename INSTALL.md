# Installation: PocketJS8 Lite on the Cardputer Zero

**Target hardware:** Linux-based M5Stack Cardputer Zero, DigiRig Mobile with the correct (tr)uSDX audio/PTT cable, (tr)uSDX transceiver, and a suitable antenna or rated dummy load. The app runs on the Cardputer; no laptop or external JS8Call engine is required during radio operation. **Release 0.3.0 is experimental and not RF-validated.**

## 1. Connect the hardware

1. Power the (tr)uSDX normally, following the radio's voltage/polarity specifications.
2. Connect the DigiRig AUDIO socket to the matching (tr)uSDX audio/PTT cable, and the cable's labelled mic/PTT and speaker plugs to the corresponding radio sockets.
3. Connect the DigiRig USB to the Cardputer's Linux USB host connection. Use a suitable powered USB hub/adapter if needed.
4. Initially leave CAT disconnected. Set the (tr)uSDX manually to USB and an appropriate JS8 dial frequency (for example **7.078 MHz** or **14.078 MHz**, subject to the applicable band plan).

The DigiRig's USB sound and serial interfaces use normal Linux kernel drivers (`snd-usb-audio` and commonly `cp210x`); the software does not include a custom audio driver. **Dire Wolf is neither required nor used.**

## 2. Install the application

Connect the Cardputer to Wi-Fi and enable SSH through its system configuration. In PowerShell on your Windows PC:

```powershell
ssh pi@CARDPUTER_IP
```

Substitute the actual Linux username/IP address; this example assumes `pi`. On the Cardputer, after the public repository has been populated:

```sh
sudo apt update
sudo apt install -y ca-certificates curl
curl -fL --retry 3 -o /tmp/cardputer-js8-lite_0.3.0_all.deb \
  https://raw.githubusercontent.com/ProtoV0id/pocketjs8-lite/main/dist/cardputer-js8-lite_0.3.0_all.deb
sudo apt install /tmp/cardputer-js8-lite_0.3.0_all.deb
```

Alternatively, download the installer directly from [`dist/`](dist/cardputer-js8-lite_0.3.0_all.deb) and copy it from your PC. In **Windows PowerShell** where the `.deb` file is located:

```powershell
scp .\cardputer-js8-lite_0.3.0_all.deb pi@CARDPUTER_IP:~/
ssh pi@CARDPUTER_IP
```

Then **on the Cardputer**:

```sh
sudo apt update
sudo apt install ./cardputer-js8-lite_0.3.0_all.deb
```

These steps install the small framebuffer interface, diagnostics, and native bridge **source**. The modem binary is built in the next step, not shipped in the installer.

## 3. Build the native JS8 decoder once

An Internet connection is required for this initial step to download the pinned GPL-3.0 modem source. The compiler can need more RAM than the Zero's available 512 MiB; the build already uses one job and reduced optimization. First install the build prerequisites:

```sh
sudo apt install -y git cmake build-essential
pocketjs8-lite-build-engine
```

The script pins the `jfrancis42/gfsk8-modem-clean` dependency to commit `bd6457e0bd4c3a10e74d1c1aaa5e86f67565168a`, builds it, runs the upstream tests, and installs `~/.local/bin/pocketjs8-lite-modem` for the **current login user**. Run this command as the same user who launches PocketJS8 Lite (don't run the builder with `sudo`).

If compilation is terminated for lack of RAM, stop and inspect the failure. Temporary swap for compilation can help; do not assume the native engine itself will meet the device's memory/performance limits until measured.

## 4. Identify the DigiRig devices

Run on the Cardputer:

```sh
pocketjs8-lite-check
lsusb
arecord -l
aplay -l
ls -l /dev/serial/by-id/ 2>/dev/null || true
dpkg --print-architecture
date -u
```

The app needs a valid **receive audio input**, **transmit audio output**, and **serial RTS PTT device**. USB device numbers can change on reconnect, so use the diagnostic output and the app's settings menu; do not assume the DigiRig will always be `hw:1,0` or `/dev/ttyUSB0`.

If you get a serial permission error, check `groups` and device group permissions. On many Debian images, your normal user needs to belong to `dialout`; log out/in after a group change. Do not run the app as root to work around permissions.

## 5. Start receiving

Open **PocketJS8 Lite** in the APPLaunch application wheel. From **Station / DigiRig**, enter your amateur callsign and Maidenhead grid, choose the actual audio interfaces, and select the PTT serial port. Initially use **Start listening** only. A real decode can take one or more complete 15-second JS8 Normal periods in a busy band. Only Normal mode is implemented.

The Cardputer's clock must be accurately synchronized to UTC for JS8 operation. Sync while you have Internet access, and check drift carefully if operating offline for extended periods.

## 6. Transmit only after confirming RX

Make your **first test on a rated dummy load**, not an unverified antenna. Verify the DigiRig radio cable, legal band/frequency, radio output level, PTT behavior and local time first. Enter a short message, inspect the exact text and frame count, unlock transmit deliberately, review the final confirmation, then submit. After transmission, confirm RTS/PTT has actually dropped. The user interface is not proof of a successful RF transmission or a recipient's decode.

PocketJS8 Lite never automatically beacons, retransmits, relays or changes your radio frequency.

## Troubleshooting

- `pocketjs8-lite-modem: not found`: repeat **step 3 as your normal app user**; the modem lives under `~/.local/bin`.
- No USB audio listed: verify USB host power/cabling and kernel USB audio driver; check `lsusb`, `dmesg`, and `arecord -l`.
- Serial PTT missing: check the DigiRig serial interface and `/dev/serial/by-id/`; verify appropriate group permissions.
- No decodes: check USB mode, dial frequency, RX gain/clipping, sample timing, decoder CPU load, and UTC clock. This modem has not yet been live-validated on the Cardputer Zero.
- Compiler killed or hanging: inspect memory using `free -h`; the native build has unusually large generated source files. Do not repeatedly retry without identifying the cause.
- No APPLaunch icon: restart the launcher or reboot and check `dpkg -s cardputer-js8-lite`.

See [README.md](README.md) for architecture, controls, limitations, license details, and the full validation plan.
