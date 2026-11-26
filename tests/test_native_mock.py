import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('g++'),'requires C++20 compiler')
class MockModemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.exe=pathlib.Path(cls.tmp.name)/'mock_modem'
        subprocess.run(['g++','-std=c++20','-O0','-Wall','-Wextra','-Werror','-pthread',
            '-I',str(ROOT/'tests/stubs'),str(ROOT/'native/modem.cpp'),
            str(ROOT/'tests/mock_gfsk8.cpp'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def command(self,*args,**kw):
        return subprocess.run([str(self.exe),*args],capture_output=True,timeout=5,**kw)
    def test_version(self):
        p=self.command('version');self.assertEqual(p.returncode,0)
        self.assertIn(b'Normal only',p.stdout)
    def test_packing(self):
        p=self.command('frames','--call','KJ7ZIM','--grid','DM33','--message','HELLO')
        self.assertEqual(json.loads(p.stdout)['frames'],1)
    def test_bad_packing_args(self):
        p=self.command('frames','--grid','DM33','--message','HELLO')
        self.assertNotEqual(p.returncode,0)
    def test_generates_pcm_with_mock_dsp(self):
        p=self.command('tx','--call','KJ7ZIM','--grid','DM33','--message','HELLO','--index','0')
        self.assertEqual(p.returncode,0)
        self.assertEqual(len(p.stdout),300000)
    def test_refuses_bad_frame_index(self):
        p=self.command('tx','--call','KJ7ZIM','--grid','DM33','--message','HELLO','--index','19')
        self.assertNotEqual(p.returncode,0)
    def test_receiver_ready_event(self):
        p=self.command('rx',input=b'')
        self.assertEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout.splitlines()[0])['event'],'ready')

if __name__=='__main__':unittest.main()
