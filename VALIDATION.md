# PocketJS8 Lite validation plan

## Completed in development environment
- Python syntax/import and framebuffer render (320×170 pixels)
- Standalone native C++ adapter compilation using header mocks
- Radio safety/validation logic tests
- Debian package metadata, paths and source integrity

## Required on Cardputer Zero after `build_engine.sh`
- [ ] `ctest` passes against the real pinned gfsk8-modem-clean library.
- [ ] `uname -m`; `dpkg --print-architecture` recorded.
- [ ] `pocketjs8-lite-check`: DigiRig capture/playback & serial shown.
- [ ] Receiver stays alive for at least 20 minutes without an ALSA xrun.
- [ ] At least one known external JS8 Normal signal actually decodes.
- [ ] Record decoder CPU, elapsed decode time and RSS under weak signal load.
- [ ] Clock alignment and drift tested against known-good reference.
- [ ] Confirm physical radio manual USB frequency matches band plan.
- [ ] With **dummy load**, confirm PTT stays idle in receive mode.
- [ ] With **dummy load**, deliberately unlock/send one short message.
- [ ] Verify correct audio output, actual RF modulation, ALC and PTT drop.
- [ ] Terminate playback mid-frame and verify immediate PTT deassertion.
- [ ] Verify second receiver can decode transmitted text.
- [ ] Verify app restart never leaves transmit enabled.

No steps in the second section were completed in this environment.
