#!/usr/bin/env python3
"""PocketJS8 Lite, a real local standalone JS8 terminal for Cardputer Zero.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import datetime as dt
import os
import queue
import re
import sys
import time
from PIL import Image, ImageDraw, ImageFont
from device import W,H,default_keyboard,run_device
from radio import Radio, audio_devices,serial_devices,ntp_status, utc_seconds

BG="#0c1719";PANEL="#15282b";CARD="#284540";LINE="#35554e"
INK="#eff5ed";MUTED="#a4b7b0";GREEN="#ace7ae";ORANGE="#f0c17f";RED="#f18a83"

def font(sz,bold=False):
    for path in (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else
                 ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
        try: return ImageFont.truetype(path,sz)
        except OSError: pass
    return ImageFont.load_default()
FT=font(14,True);FB=font(14);FS=font(10);FM=font(12)

def fit(s, face, width):
    s=str(s)
    while s and face.getlength(s)>width:
        s=s[:-1]
    return s

def wrap(text,face=FM,width=295):
    lines=[]
    for para in str(text).replace('\r\n','\n').replace('\r','\n').split('\n'):
        if not para:
            lines.append('')
            continue
        line=''
        for word in para.split(' '):
            test=(line+' '+word).strip() if line else word
            if face.getlength(test)<=width:
                line=test
            elif line:
                lines.append(line)
                line=word
            else:
                line=word
            while face.getlength(line)>width and len(line)>1:
                part=fit(line,face,width)
                lines.append(part)
                line=line[len(part):]
        lines.append(line)
    return lines

class UI:
    def __init__(self, radio=None, demo=False):
        self.r=radio or Radio()
        self.demo=demo
        self.mode='menu'
        self.toast=''
        self.last_ntp=None
        self.ntp_checked=0
        self.last_tick=-1
        self.review_snapshot=None
        if self.r.configured() and self.r.native_installed() and not demo:
            ok,msg=self.r.start_rx()
            self.toast=msg
        self.home()

    def menu(self,title,items,back=None):
        self.mode='menu';self.title=title;self.items=items
        self.sel=0;self.top=0;self.back=back or self.home
        if not items:self.items=[('Back',self.back)]

    def view(self,title,text,back=None):
        self.mode='view';self.title=title
        self.lines=wrap(text)
        self.top=0;self.back=back or self.home
        self.accept=None

    def edit(self,title,text,done,back,limit=64):
        self.mode='edit';self.title=title
        self.text=str(text);self.cursor=len(self.text)
        self.done=done;self.back=back;self.edit_limit=limit

    def home(self):
        self.menu('POCKETJS8 LITE',[
          ('Live messages',self.activity),
          ('Compose short message',self.compose),
          (('Stop listening' if self.r.rx_state!='STOPPED' else 'Start listening'),self.toggle_rx),
          ('Station / DigiRig',self.settings),
          ('Transmit controls',self.tx_controls),
          ('Station diagnostics',self.diagnostics),
          ('Help / limits',self.help),
          ('Exit',self.quit),
        ],self.quit)

    def quit(self):
        self.r.lock()
        self.mode='quit'

    def activity(self):
        things=list(reversed(self.r.rxs[-60:]))
        items=[]
        for e in things:
            text=str(e.get('text') or e.get('raw') or '(decode)')
            label=f"{int(e.get('snr',0)):+d} {text}"
            items.append((label,lambda e=e:self.open_decode(e)))
        if not things:
            items.append(('No decoded messages yet',lambda:self.view('NO DECODES',
                'Start listening, tune the radio to an occupied JS8 frequency, and check the clock and receive audio.',self.activity)))
        items += [('Back',self.home)]
        self.menu('LIVE ACTIVITY',items,self.home)

    def open_decode(self,e):
        self.view('RECEIVED',
           'UTC: '+str(e.get('received_at',''))+'\n'+
           f"Signal: {e.get('snr','?')} dB   Offset: {e.get('offset','?')} Hz\n\n"+
           str(e.get('text') or '')+'\n\nFrame: '+str(e.get('raw','')),
           self.activity)

    def toggle_rx(self):
        if self.r.rx_state!='STOPPED':
            self.r.stop_rx();self.toast='Receive stopped';self.home()
        else:
            ok,msg=self.r.start_rx();self.toast=msg
            if ok:self.home()
            else:self.view('RX NOT READY',msg,self.home)

    def compose(self):
        text=self.r.cfg['draft']
        self.menu('COMPOSE',[
           ('Text: '+(text or '[empty]'),self.edit_message),
           ('Review frames and send',self.review),
           ('Clear draft',self.clear_confirm),
           ('Back',self.home),
        ],self.home)

    def edit_message(self):
        self.edit('SHORT MESSAGE',self.r.cfg['draft'],lambda s:self.save_draft(s),self.compose,48)

    def save_draft(self,text):
        self.r.cfg['draft']=text
        self.r.save();self.compose()

    def clear_confirm(self):
        self.menu('CLEAR DRAFT?', [('No, keep message',self.compose),
                   ('Yes, delete',lambda:self.save_draft(''))],self.compose)

    def review(self):
        try:self.review_snapshot=self.r.review(self.r.cfg['draft'])
        except Exception as exc:
            self.view('CANNOT SEND',str(exc),self.compose);return
        s=self.review_snapshot
        self.view('CHECK MESSAGE',
          f"From: {s['call']}  Grid: {s['grid']}\n"
          f"JS8 Normal: {s['frames']} frame(s), at least {15*s['frames']} sec TX\n"
          f"TX audio: {s['audio'] or 'NOT SET'}\nPTT port: {s['port'] or 'NOT SET'}\n\n{s['message']}\n\n"
          'Press ENTER to continue to the explicit send confirmation.',self.compose)
        self.accept=self.send_confirmation

    def send_confirmation(self):
        if not self.r.tx_unlocked:
            self.view('TX LOCKED',
                 'Open Transmit controls and deliberately unlock TX before sending. '
                 'Confirm UTC clock, antenna/dummy load, audio levels and PTT first.',self.compose)
            return
        if not self.review_snapshot:
            self.view('REVIEW EXPIRED','Review the message again.',self.compose);return
        self.menu('SEND OVER RF?',[
            ('CANCEL / keep draft',self.compose),
            ('YES: send queued frames',self.send_reviewed)
        ],self.compose)

    def send_reviewed(self):
        ok,msg=self.r.transmit(self.review_snapshot)
        self.review_snapshot=None
        if ok:
            self.view('TX SCHEDULED',msg+'\n\nTX unlock is consumed. Return to Transmit controls to halt if necessary. '
                      'Playing audio does NOT confirm reception.',self.home)
        else:self.view('TX REFUSED',msg,self.compose)

    def tx_controls(self):
        items=[('Lock TX now',self.lock_tx)] if self.r.tx_unlocked else [('Unlock TX for one message',self.unlock_tx)]
        if self.r.tx_state not in ('IDLE','COMPLETE'):
            items.append(('HALT current TX',self.halt_confirm))
        items += [('TX status: '+self.r.tx_state[:40],lambda:self.view('TX STATUS',self.r.tx_state,self.tx_controls)),
                  ('Back',self.home)]
        self.menu('TRANSMIT CONTROL',items,self.home)

    def lock_tx(self):
        self.r.lock();self.toast='TX locked';self.tx_controls()

    def unlock_tx(self):
        self.menu('UNLOCK TX?',[
            ('NO: stay receive-only',self.tx_controls),
            ('YES: clock/RF/PTT checked',self.allow_tx),
        ],self.tx_controls)

    def allow_tx(self):
        if not self.r.unlock():
            self.view('PTT FAULT','Unable to confirm that PTT was released. Inspect the DigiRig and restart the app.',self.tx_controls)
            return
        self.toast='TX unlocked for one reviewed message';self.tx_controls()

    def halt_confirm(self):
        self.menu('HALT TX?',[
             ('Cancel',self.tx_controls),
             ('STOP audio and PTT now',self.halt_tx)
        ],self.tx_controls)

    def halt_tx(self):
        self.r.halt();self.toast='Stop requested';self.home()

    def settings(self):
        c=self.r.cfg
        self.menu('STATION / DIGIRIG',[
           ('Call: '+(c['call'] or '[set]'),lambda:self.field('call')),
           ('Grid: '+(c['grid'] or '[set]'),lambda:self.field('grid')),
           ('RX audio: '+(c['rx_audio'] or '[choose]'),lambda:self.pick_audio('rx_audio')),
           ('TX audio: '+(c['tx_audio'] or '[choose]'),lambda:self.pick_audio('tx_audio')),
           ('PTT port: '+(c['ptt_port'] or '[choose]'),self.pick_serial),
           ('Back',self.home)
        ],self.home)

    def field(self,key):
        def done(value):
            self.r.cfg[key]=value.strip().upper();self.r.save();self.settings()
        self.edit({'call':'CALLSIGN','grid':'MAIDENHEAD GRID'}[key],self.r.cfg[key],done,self.settings,14)

    def set_hardware(self,key,value):
        if self.r.rx_state!='STOPPED':
            self.r.stop_rx()
            self.toast='RX stopped. Restart after device change.'
        self.r.cfg[key]=value
        self.r.save();self.settings()

    def pick_audio(self,key):
        items=audio_devices('arecord' if key=='rx_audio' else 'aplay')
        options=[(e['label'],lambda device=e['device']:self.set_hardware(key,device)) for e in items]
        options += [('Manual ALSA device entry',lambda:self.manual_hardware(key)),('Back',self.settings)]
        self.menu('RX AUDIO' if key=='rx_audio' else 'TX AUDIO',options,self.settings)

    def pick_serial(self):
        options=[(os.path.basename(p),lambda path=p:self.set_hardware('ptt_port',path)) for p in serial_devices()]
        options += [('Manual serial path',lambda:self.manual_hardware('ptt_port')),('Back',self.settings)]
        self.menu('DIGIRIG PTT',options,self.settings)

    def manual_hardware(self,key):
        self.edit('AUDIO DEVICE' if key!='ptt_port' else 'SERIAL PATH',self.r.cfg[key],
                  lambda s:self.set_hardware(key,s.strip()),self.settings,100)

    def diagnostics(self):
        c=self.r.cfg
        clock=('NTP synced' if self.last_ntp else 'NTP unverified')
        self.view('LOCAL DIAGNOSTICS',
            f"UTC: {utc_seconds()}\nClock: {clock}\n"
            f"Modem: {'installed' if self.r.native_installed() else 'NOT BUILT'}\n"
            f"Receiver: {self.r.rx_state}\nTX: {'UNLOCKED' if self.r.tx_unlocked else 'LOCKED'}\n"
            f"RX audio: {c['rx_audio'] or 'not configured'}\n"
            f"TX audio: {c['tx_audio'] or 'not configured'}\n"
            f"PTT: {c['ptt_port'] or 'not configured'}\n"
            "Rig: MANUAL USB, verify actual dial\n"
            "Modem: JS8 Normal, 15-second slots\n"
            "No desktop JS8Call or Dire Wolf needed.",self.home)

    def help(self):
        self.view('FIELD NOTES',
          'Standalone JS8 Normal receiver with manually reviewed short-message TX.\n\n'
          'Connect DigiRig USB to Zero. DigiRig audio/PTT cable to (tr)uSDX. '
          'Tune (tr)uSDX manually to 7.078 MHz USB for 40m or 14.078 MHz USB for 20m.\n\n'
          'RX auto-starts after configuration, provided native modem is built. '
          'PTT uses serial RTS; CAT is deliberately absent. Keep TX locked until tested.\n\n'
          'F/X navigate, Enter select, Esc back; Shift+Enter saves text. '
          'Correct UTC essential. Tests and first RF session required.',self.home)

    def poll(self):
        # Process receive events, refresh UTC time label, and display real statuses.
        for _ in range(20):
            try:event=self.r.events.get_nowait()
            except queue.Empty: break
            if event['event']=='rx_event':
                e=event['data']
                if e.get('event')=='decode':
                    self.toast='Decoded: '+str(e.get('text',''))[:30]
                    if self.mode=='menu' and self.title=='LIVE ACTIVITY':
                        prior_sel,prior_top=self.sel,self.top
                        self.activity()
                        self.sel=min(prior_sel,len(self.items)-1)
                        self.top=min(prior_top,self.sel)
                elif e.get('event')=='warning':self.toast=str(e.get('message',''))
            elif event['event']=='tx_status':self.toast=str(event.get('status',''))
            elif event['event']=='rx_stopped':self.toast=str(event.get('message',''))
        if time.monotonic()-self.ntp_checked>30:
            self.last_ntp=ntp_status() if not self.demo else True
            self.ntp_checked=time.monotonic()

    def input(self,key,char=None,ctrl=False):
        if self.mode=='menu':
            if key in ('UP','LEFT'):
                self.sel=(self.sel-1)%len(self.items)
            elif key in ('DOWN','RIGHT'):
                self.sel=(self.sel+1)%len(self.items)
            elif key=='ENTER':
                self.items[self.sel][1]()
            elif key=='ESC':self.back()
        elif self.mode=='view':
            if key in ('UP','LEFT'):
                self.top=max(0,self.top-1)
            elif key in ('DOWN','RIGHT'):
                self.top=min(max(0,len(self.lines)-6),self.top+1)
            elif key=='ENTER' and getattr(self,'accept',None):
                callback=self.accept;self.accept=None;callback()
            elif key in ('ENTER','ESC'):
                self.accept=None;self.back()
        elif self.mode=='edit':
            if key=='ESC':self.back()
            elif key=='LEFT':self.cursor=max(0,self.cursor-1)
            elif key=='RIGHT':self.cursor=min(len(self.text),self.cursor+1)
            elif key=='BACKSPACE' and self.cursor:
                self.text=self.text[:self.cursor-1]+self.text[self.cursor:]
                self.cursor-=1
            elif key=='ENTER':
                cb=self.done;cb(self.text)
            elif char and len(self.text)<self.edit_limit:
                self.text=self.text[:self.cursor]+char+self.text[self.cursor:]
                self.cursor+=1

    def draw(self):
        im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
        d.rectangle((0,0,319,28),fill=PANEL)
        d.rectangle((0,0,3,28),fill=GREEN)
        d.line((0,28,319,28),fill=LINE)
        d.text((10,6),fit(self.title,FT,190),font=FT,fill=INK)
        pill='TX' if self.r.tx_state.startswith('ON AIR') else ('LOCK' if not self.r.tx_unlocked else 'ARMED')
        c=RED if pill=='TX' else ORANGE if pill=='ARMED' else GREEN
        d.rounded_rectangle((228,6,269,22),radius=4,fill=CARD)
        d.text((232,8),fit(pill,FS,37),fill=c,font=FS)
        d.text((275,9),utc_seconds()[:5]+'Z',fill=MUTED,font=FS)
        if self.mode=='menu':
            top=self.top
            if self.sel<top:self.top=self.sel
            if self.sel>=self.top+4:self.top=self.sel-3
            for i,(label,_) in enumerate(self.items[self.top:self.top+4]):
                ix=i+self.top; y=33+29*i; selected=ix==self.sel
                if selected:
                    d.rounded_rectangle((7,y-1,311,y+25),radius=4,fill=CARD,outline=LINE)
                    d.rectangle((9,y+4,12,y+20),fill=GREEN)
                else:d.line((15,y+25,310,y+25),fill=LINE)
                d.text((19,y+5),f"{ix+1:02}",font=FS,fill=GREEN if selected else MUTED)
                d.text((43,y+2),fit(label,FB,259),font=FB,fill=INK if selected else MUTED)
        elif self.mode=='edit':
            shown=self.text[:self.cursor]+'|'+self.text[self.cursor:]
            lines=wrap(shown,FB)
            for i,line in enumerate(lines[-5:]):
                d.text((12,33+22*i),fit(line,FB,296),font=FB,fill=INK)
        else:
            for i,line in enumerate(self.lines[self.top:self.top+6]):
                d.text((12,34+18*i),fit(line,FM,294),font=FM,fill=INK)
        d.rectangle((0,150,319,169),fill=PANEL)
        d.line((0,150,319,150),fill=LINE)
        hint=('F/X MOVE · ENTER SELECT · ESC BACK' if self.mode=='menu' else
              'ENTER SAVE · ESC CANCEL' if self.mode=='edit' else
              'F/X SCROLL · ENTER / ESC BACK')
        if self.toast and self.mode!='edit':hint=self.toast
        d.text((10,154),fit(hint,FS,302),font=FS,fill=ORANGE if self.toast else MUTED)
        return im


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview',metavar='PNG')
    parser.add_argument('--framebuffer',default=os.getenv('APPLAUNCH_LINUX_FBDEV_DEVICE') or '/dev/fb0')
    parser.add_argument('--keyboard',default=default_keyboard())
    opts=parser.parse_args()
    os.umask(0o077)
    radio=Radio()
    ui=UI(radio,demo=bool(opts.preview))
    try:
        if opts.preview:
            ui.toast='PREVIEW - NOT CONNECTED'
            ui.draw().save(opts.preview)
        else:run_device(ui,opts.framebuffer,opts.keyboard)
    finally:radio.close()

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError) as e:
        print('PocketJS8 Lite: '+str(e),file=sys.stderr);sys.exit(1)
