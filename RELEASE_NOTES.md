# PocketJS8 Lite 0.3.0 beta

**Experimental, standalone JS8 Normal-mode receiver and short-message transmitter** for a Linux-based M5Stack Cardputer Zero with DigiRig Mobile and (tr)uSDX.

- Native modem bridge built from the pinned `gfsk8-modem-clean` open-source library.
- DigiRig USB audio capture/playback and RTS PTT via standard Linux devices.
- Framebuffer/keyboard UI, local receive log, short-message composition and explicit transmit confirmation.
- Receive-first operation, manual radio tuning, no CAT, no automatic beacon or relay.
- GPL-3.0-or-later application code; GPL-3.0 modem dependency (see LICENSE-NOTICE.md).

**Important:** This `.deb` installs the application and one-time native engine builder, not a precompiled JS8 DSP binary. Run `pocketjs8-lite-build-engine` with network access and build tools after installing the package. No network is required for normal operation after a successful build.

**Hardware status:** 29 host software/mock tests passed. This is *not* a claim of validated DigiRig audio, on-air decoding, radio PTT behavior or Raspberry Pi Zero sustained decoding speed. Test receiving first and use a dummy load for any initial transmit check.

See [INSTALL.md](INSTALL.md) and [VALIDATION.md](VALIDATION.md).
