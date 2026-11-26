#!/usr/bin/env python3
"""Offline-capable setup diagnostic for PocketJS8 Lite."""
import os
import platform
import subprocess
from radio import Radio,audio_devices,serial_devices,ntp_status,utc_seconds

def main():
    r=Radio()
    print('PocketJS8 Lite 0.3.0 | local hardware check')
    print('Machine:',platform.machine(), '| UTC:',utc_seconds())
    print('Clock NTP status:', 'synchronized' if ntp_status() else 'NOT CONFIRMED; verify UTC before TX')
    print('Native JS8 modem:',r.native if r.native_installed() else 'NOT BUILT')
    print('Call:',r.cfg['call'] or '[not set]', '| Grid:',r.cfg['grid'] or '[not set]')
    print('Selected RX:',r.cfg['rx_audio'] or '[none]')
    print('Selected TX:',r.cfg['tx_audio'] or '[none]')
    print('Selected RTS:',r.cfg['ptt_port'] or '[none]')
    for tool in ('arecord','aplay'):
        print('\n'+tool+' devices:')
        for dev in audio_devices(tool): print(' ',dev['device'],dev['label'])
    print('\nSerial devices:')
    for dev in serial_devices(): print(' ',dev)
    try:
        cp=subprocess.run(['lsusb'],text=True,capture_output=True,timeout=3)
        print('\nUSB:');print(cp.stdout.strip() or '[not available]')
    except (OSError,subprocess.TimeoutExpired):print('USB listing unavailable')
    print('\nNo radio keying, recording, transmit audio, or configuration changes were performed.')

if __name__=='__main__':
    main()
