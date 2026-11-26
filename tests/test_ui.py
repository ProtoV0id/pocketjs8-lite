import unittest
from unittest.mock import Mock
from PIL import Image
import pocketjs8_lite

class FakeRadio:
    def __init__(self):
        self.cfg={'call':'KJ7ZIM','grid':'DM33','rx_audio':'plughw:1,0','tx_audio':'plughw:1,0',
             'ptt_port':'/dev/ttyUSB0','draft':'HELLO'}
        self.tx_state='IDLE';self.rx_state='STOPPED';self.tx_unlocked=False
        self.rxs=[]
        import queue
        self.events=queue.Queue()
        self.send_calls=0
    def native_installed(self):return True
    def configured(self):return False
    def review(self,text):return dict(message=text,call='KJ7ZIM',grid='DM33',audio='plughw:1,0',
                                       port='/dev/ttyUSB0',frames=1)
    def transmit(self,s):self.send_calls+=1;return True,'scheduled'
    def unlock(self):self.tx_unlocked=True;return True
    def lock(self):self.tx_unlocked=False
    def save(self):pass
    def start_rx(self):self.rx_state='LISTENING';return True,'started'
    def stop_rx(self):self.rx_state='STOPPED'

class UITest(unittest.TestCase):
    def setUp(self):
        self.radio=FakeRadio();self.ui=pocketjs8_lite.UI(self.radio,demo=True)
    def test_screen_resolution(self):self.assertEqual(self.ui.draw().size,(320,170))
    def test_default_tx_locked(self):self.assertFalse(self.ui.r.tx_unlocked)
    def test_receives_activity(self):
        self.ui.activity()
        self.assertEqual(self.ui.title,'LIVE ACTIVITY')
        self.radio.rxs.append({'event':'decode','text':'K7ABC CQ','snr':-8})
        self.ui.activity()
        self.assertTrue(any('K7ABC' in label for label,_ in self.ui.items))
    def test_review_does_not_transmit(self):
        self.ui.review()
        self.assertEqual(self.ui.mode,'view')
        self.assertEqual(self.radio.send_calls,0)
        self.ui.input('ENTER')
        self.assertEqual(self.ui.title,'TX LOCKED')
        self.assertEqual(self.radio.send_calls,0)
    def test_full_two_step_confirmation(self):
        self.radio.unlock()
        self.ui.review()
        self.ui.input('ENTER')
        self.assertEqual(self.ui.title,'SEND OVER RF?')
        self.assertEqual(self.ui.sel,0)
        self.ui.input('ENTER')
        self.assertEqual(self.radio.send_calls,0)
        self.radio.unlock();self.ui.review();self.ui.input('ENTER')
        self.ui.input('DOWN');self.ui.input('ENTER')
        self.assertEqual(self.radio.send_calls,1)
    def test_unrelated_view_cannot_reuse_old_accept(self):
        self.radio.unlock();self.ui.review();self.assertIsNotNone(self.ui.accept)
        self.ui.view('INFO','Nothing to send')
        self.ui.input('ENTER')
        self.assertEqual(self.radio.send_calls,0)
    def test_text_editor_cancel(self):
        self.ui.edit_message();self.ui.input('CHAR','X')
        self.ui.input('ESC')
        self.assertEqual(self.radio.cfg['draft'],'HELLO')
    def test_unlocked_menu_defaults_cancel(self):
        self.ui.unlock_tx()
        self.assertEqual(self.ui.sel,0)
        self.ui.input('ENTER');self.assertFalse(self.radio.tx_unlocked)

if __name__=='__main__':unittest.main()
