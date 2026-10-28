"""Version-1 low-voltage serial bench protocol. CRC detects corruption, not forgery."""
import threading
import time
import zlib
from .core import APPROACHES, GROUPS, Timing

MAX_FRAME=128
STAGES=('ALL_RED','GREEN','YELLOW')
FAULTS={0:None,1:'bad_frame',2:'bad_session',3:'replay',4:'lease_lost',5:'illegal_change',6:'manual_stop',7:'output_mismatch'}


def frame(payload):
    raw=payload.encode('ascii')
    if len(raw)>115 or any(c<32 or c>126 for c in raw) or b'*' in raw:
        raise ValueError('Invalid serial payload')
    return raw+b'*'+f'{zlib.crc32(raw):08x}'.encode()+b'\n'


def decode(raw):
    if isinstance(raw,bytes) and raw.endswith(b"\r\n"):
        raw=raw[:-2]+b"\n"
    if not isinstance(raw,bytes) or not raw.endswith(b'\n') or len(raw)>MAX_FRAME:
        raise ValueError('Truncated or oversized serial reply')
    body,checksum=raw[:-1].split(b'*')
    if len(checksum)!=8 or checksum!=f'{zlib.crc32(body):08x}'.encode():
        raise ValueError('Serial reply checksum mismatch')
    fields=body.decode('ascii').split(',')
    if len(fields)!=8 or fields[0]!='R' or len(fields[1])!=16 or any(c not in '0123456789abcdef' for c in fields[1]):
        raise ValueError('Invalid serial reply fields')
    if any(not s.isascii() or not s.isdecimal() or len(s)>10 for s in fields[2:]):
        raise ValueError('Invalid serial reply numbers')
    seq,stage,phase,fault,bits,clock=map(int,fields[2:])
    if not (0<=seq<=0xffffffff and stage<3 and phase<2 and fault in FAULTS and bits<64 and clock<=0xffffffff):
        raise ValueError('Serial reply out of bounds')
    lamps=dict.fromkeys(APPROACHES,'RED')
    if stage:
        for a in GROUPS[('NS','EW')[phase]]:lamps[a]=STAGES[stage]
    expected=9 if stage==0 else ((4 if stage==1 else 2)|8) if phase==0 else (1|(32 if stage==1 else 16))
    if bits!=expected:raise ValueError('GPIO readback does not match reported stage')
    return {'stage':STAGES[stage],'phase':('NS','EW')[phase],'lamps':lamps,'fault':FAULTS[fault],
            'reason':'board_readback','acknowledged_sequence':seq,'board_clock_ms':clock,
            'boot_session':fields[1],'gpio_bits':bits,'physical_hardware':False,
            'readback_kind':'GPIO logic level; lamp current/light not measured','physical_lamp_verified':False}


class SerialBenchAdapter:
    name='esp32s3-low-voltage-bench'
    def __init__(self,timing=None,*,port=None,stream=None):
        timing=timing or Timing()
        if (timing.min_green,timing.max_green,timing.yellow,timing.all_red)!=(8,60,3,2):
            raise ValueError('Board profile v1 requires bench timing 8/60/3/2 seconds')
        self.physical_hardware = stream is None
        if stream is None:
            if not port:raise ValueError('Explicit serial port required; no automatic port scanning')
            try:import serial
            except ImportError:raise RuntimeError('Install sabz-edge[hardware] for physical serial transport') from None
            stream=serial.Serial(port,115200,timeout=.02,write_timeout=.15)
        self.stream=stream;self.lock=threading.Lock();self.failed=False;self.closed=False
        self.readback=None;self.last=None;self.sequence=0;self.boot=None
        try:
            self.readback=self._read(time.monotonic()+3)
            if self.readback['fault'] or self.readback['acknowledged_sequence']!=0 or self.readback['stage']!='ALL_RED':
                raise RuntimeError('Board must be locally reset, healthy and idle all-red before attachment')
            self.boot=self.readback['boot_session']
        except Exception:
            stream.close();raise
    def _read(self,deadline):
        while time.monotonic()<deadline:
            raw=self.stream.read_until(b'\n',MAX_FRAME)
            if not raw:continue
            result=decode(raw)
            result['physical_hardware']=self.physical_hardware
            if self.boot is not None and result['boot_session']!=self.boot:
                raise RuntimeError('Board reboot/session changed; automatic reattachment disabled')
            return result
        raise RuntimeError('Board acknowledgement timeout')
    def _exchange(self,payload,expected=None):
        if self.failed or self.closed:raise RuntimeError('Serial bench adapter unavailable')
        try:
            raw=frame(payload)
            if self.stream.write(raw)!=len(raw):raise RuntimeError('Partial serial write')
            deadline=time.monotonic()+.2
            while True:
                result=self._read(deadline)
                # Periodic readback can precede the reply. Never accept an old ACK.
                if expected is None or result['acknowledged_sequence']>=expected:break
            if expected is not None and result['acknowledged_sequence']!=expected:raise RuntimeError('Unexpected command acknowledgement')
            if result['fault']:raise RuntimeError('Board fault: '+result['fault'])
            self.readback=result
            return result
        except Exception:
            self.failed=True;raise
    def apply(self,command):
        with self.lock:
            seq=command['command_sequence']
            if type(seq) is not int or not self.sequence<seq<=0xffffffff:raise ValueError('Serial sequence exhausted or replayed')
            stage=STAGES.index(command['stage']);phase=('NS','EW').index(command['phase'])
            expected=dict.fromkeys(APPROACHES,'RED')
            if stage:
                for a in GROUPS[command['phase']]:expected[a]=command['stage']
            if command['lamps']!=expected:raise ValueError('Conflicting lamp proposal')
            lease=command['lease_s']
            if type(lease) not in (int,float) or not .1<=lease<=.5:raise ValueError('Invalid command lease')
            fault=int(bool(command.get('fault')) or command.get('reason') in ('sensor_unavailable','metric_sensor_unavailable'))
            self._exchange(f'C,{self.boot},{seq},{stage},{phase},{fault},{round(lease*1000)}',seq)
            self.sequence=seq;self.last=dict(command)
    def status(self):
        with self.lock:return self._exchange(f'Q,{self.boot}')
    def close(self):
        with self.lock:
            if self.closed:return
            try:
                if not self.failed and self.sequence<0xffffffff:
                    seq=self.sequence+1
                    self._exchange(f'C,{self.boot},{seq},0,0,1,100',seq)
            except Exception:pass
            finally:self.closed=True;self.stream.close()
