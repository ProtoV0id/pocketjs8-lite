# Licenses

PocketJS8 Lite's own Python, C++, shell, and packaging code: **GPL-3.0-or-later**.
The Cardputer framebuffer/keyboard adapter is adapted from the user's earlier
PocketLink/PocketJS8 work; its copyright ownership is unchanged.

The modem is not contained in the Debian installer: build_engine.sh obtains
`jfrancis42/gfsk8-modem-clean` at commit
`bd6457e0bd4c3a10e74d1c1aaa5e86f67565168a` and links its GPL-3.0 library
into the local native executable. Keep this notice and the upstream source
available when redistributing a binary. Its vendored KissFFT component uses
its own upstream MIT license.

No proprietary radio software or firmware is redistributed here.
