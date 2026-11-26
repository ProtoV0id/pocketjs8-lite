import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import radio

class RadioTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.dir=Path(self.temp.name)
        self.patches=[patch.object(radio,'STATE',self.dir),
                      patch.object(radio,'CONFIG',self.dir/'config.json'),
                      patch.object(radio,'LOG',self.dir/'rx.jsonl')]
        for p in self.patches:p.start()
        self.r=radio.Radio(native=self.dir/'mock_modem')
    def tearDown(self):
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def ready(self):
        self.r.cfg.update(call='KJ7ZIM',grid='DM33',rx_audio='plughw:1,0',
                          tx_audio='plughw:1,0',ptt_port='/dev/ttyUSB0',draft='HI')
    def test_defaults_receive_only(self):
        self.assertFalse(self.r.tx_unlocked)
        self.assertEqual(self.r.rx_state,'STOPPED')
        self.assertFalse(self.r.native_installed())
    def test_config_roundtrip_restrict_permissions(self):
        self.ready();self.r.save()
        self.assertEqual(radio.load_config()['call'],'KJ7ZIM')
        self.assertEqual(self.r.cfg['draft'],json.loads(radio.CONFIG.read_text())['draft'])
        self.assertEqual(radio.CONFIG.stat().st_mode&0o777,0o600)
    def test_no_native_no_rx(self):
        self.ready();ok,msg=self.r.start_rx()
        self.assertFalse(ok);self.assertIn('Build',msg)
    def test_audio_parser(self):
        text='''**** List of CAPTURE Hardware Devices ****
card 1: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
card 2: Sound [Other audio], device 0: Fake [Fake]
'''
        with patch.object(radio.subprocess,'run',return_value=Mock(stdout=text)):
            ds=radio.audio_devices('arecord')
        self.assertEqual(ds[0]['device'],'plughw:1,0')
        self.assertEqual(len(ds),2)
    def test_audio_commands_are_whitelisted(self):
        with self.assertRaises(ValueError):radio.audio_devices('evil')
    def test_preview_short_text(self):
        self.ready()
        with patch.object(self.r,'native_installed',return_value=True),\
             patch.object(radio.subprocess,'run',return_value=Mock(returncode=0,stdout='{"frames":2}',stderr='')):
            s=self.r.review('Hello from AZ')
        self.assertEqual(s['frames'],2)
        self.assertEqual(s['message'],'HELLO FROM AZ')
    def test_refuses_long_draft(self):
        self.ready()
        with patch.object(self.r,'native_installed',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'1-48'):self.r.review('a'*49)
    def test_refuses_invalid_callsign(self):
        self.ready();self.r.cfg['call']='x'
        with patch.object(self.r,'native_installed',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'callsign'):self.r.review('hello')
    def test_refuses_invalid_grid(self):
        self.ready();self.r.cfg['grid']='XXXX'
        with patch.object(self.r,'native_installed',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'grid'):self.r.review('hello')
    def test_refuses_extra_frames(self):
        self.ready()
        with patch.object(self.r,'native_installed',return_value=True),\
             patch.object(radio.subprocess,'run',return_value=Mock(returncode=0,stdout='{"frames":5}',stderr='')):
            with self.assertRaisesRegex(RuntimeError,'Limit'):self.r.review('hello')
    def test_tx_requires_unlock_and_valid_devices(self):
        self.ready()
        snapshot={'message':'HI','call':'KJ7ZIM','grid':'DM33','frames':1,'audio':'plughw:1,0','port':'/dev/ttyUSB0'}
        self.assertFalse(self.r.transmit(snapshot)[0]);self.r.unlock()
        snapshot['audio']='randomname'
        self.assertFalse(self.r.transmit(snapshot)[0]);self.r.lock()
        self.assertFalse(self.r.tx_unlocked)
    def test_tx_lock_consumed_on_submit(self):
        self.ready()
        s={'message':'HI','call':'KJ7ZIM','grid':'DM33','frames':1,'audio':'plughw:1,0','port':'/dev/ttyUSB0'}
        with patch.object(self.r,'_transmit_work',lambda snap: None):
            self.r.unlock();ok,_=self.r.transmit(s)
            self.assertTrue(ok)
            self.assertFalse(self.r.tx_unlocked)
            self.r._tx_thread.join(timeout=3)
    def test_audio_mismatch_never_transmits(self):
        self.ready();self.r.unlock()
        s={'message':'HI','call':'KJ7ZIM','grid':'DM33','frames':1,'audio':'plughw:2,0','port':'/dev/ttyUSB0'}
        self.assertFalse(self.r.transmit(s)[0])
    def test_rx_log_retained(self):
        radio.append_rx({'event':'decode','text':'CQ CQ TEST'})
        self.assertEqual(radio.recent_rx()[0]['text'],'CQ CQ TEST')
        self.assertEqual(radio.LOG.stat().st_mode&0o777,0o600)
    def test_dekey_error_closes_fd(self):
        with patch.object(radio.fcntl,'ioctl',side_effect=OSError('USB missing')),\
             patch.object(radio.os,'close') as close:
            self.r._release_ptt(42)
        close.assert_called_once_with(42)
        self.assertIn('PTT dekey ioctl failed',self.r.events.get()['status'])
        self.assertTrue(self.r._ptt_fault)
        self.assertFalse(self.r.unlock())

if __name__=='__main__':unittest.main()
