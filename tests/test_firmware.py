"""Compile and exercise the SAME C++ core used by ESP32 firmware, not a rewrite."""
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from sabz_edge.serial_bench import decode,frame,SerialBenchAdapter
from sabz_edge.core import Timing

BOOT='0123456789abcdef'

class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('g++')
        if not compiler:raise unittest.SkipTest('C++ compiler unavailable: native firmware tests not executed')
        cls.directory=tempfile.TemporaryDirectory()
        cls.executable=str(Path(cls.directory.name)/'controller-host.exe')
        source=Path(__file__).resolve().parents[1]/'firmware/native/controller_host.cpp'
        subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror','-O2',str(source),'-o',cls.executable],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()
    def setUp(self):
        self.process=subprocess.Popen([self.executable],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.sequence=0
    def tearDown(self):
        self.process.stdin.close();self.process.wait(timeout=3)
        self.process.stdout.close();self.process.stderr.close()
    def exchange(self,now,payload=None,clear=True,stop=True):
        raw=frame(payload).rstrip(b'\n') if payload is not None else b'-'
        self.process.stdin.write(f'{now} {int(clear)} {int(stop)} '.encode()+raw+b'\n');self.process.stdin.flush()
        return decode(self.process.stdout.readline())
    def command(self,now,stage=1,phase=0,fault=0,**kwargs):
        self.sequence+=1
        return self.exchange(now,f'C,{BOOT},{self.sequence},{stage},{phase},{fault},500',**kwargs)
    def test_clearance_and_local_minimum(self):
        self.assertEqual(self.command(2000,clear=False)['stage'],'ALL_RED')
        self.assertEqual(self.command(2100)['stage'],'GREEN')
        self.assertEqual(self.command(2200,stage=2)['stage'],'GREEN')
    def test_lease_expiry_cannot_be_reset_by_queries_or_fresh_commands(self):
        self.command(2000)
        self.assertEqual(self.exchange(2400,f'Q,{BOOT}')['stage'],'GREEN')
        result=self.exchange(2500,f'Q,{BOOT}')
        self.assertEqual((result['stage'],result['fault']),('YELLOW','lease_lost'))
        self.assertEqual(self.command(5499)['stage'],'YELLOW')
        self.assertEqual(self.command(5500)['stage'],'ALL_RED')
        self.assertEqual(self.command(8000)['stage'],'ALL_RED')
    def test_local_maximum_with_continuous_green_proposals(self):
        self.command(2000)
        state=None
        for now in range(2250,62001,250):state=self.command(now)
        self.assertEqual(state['stage'],'YELLOW')
        self.assertIsNone(state['fault'])
    def test_direct_conflicting_green_faults_and_clears(self):
        self.command(2000)
        state=self.command(2100,phase=1)
        self.assertEqual((state['stage'],state['fault']),('YELLOW','illegal_change'))
    def test_manual_loop_break_and_replay_latch(self):
        self.command(2000)
        state=self.exchange(2010,f'Q,{BOOT}',stop=False)
        self.assertEqual(state['fault'],'manual_stop')
        self.assertEqual(self.command(2020)['stage'],'YELLOW')
    def test_old_session_rejected(self):
        state=self.exchange(2000,'C,0000000000000001,1,1,0,0,500')
        self.assertEqual(state['fault'],'bad_session')
        self.assertEqual(self.command(3000)['stage'],'ALL_RED')
    def test_replayed_command_is_fault(self):
        payload=f'C,{BOOT},1,1,0,0,500'
        self.exchange(2000,payload)
        self.assertEqual(self.exchange(2100,payload)['fault'],'replay')
    def test_unsigned_clock_wrap_keeps_lease_and_clearance(self):
        self.command(0xffffff00)
        self.assertEqual(self.exchange(0x20,f'Q,{BOOT}')['stage'],'GREEN')
        state=self.exchange(0x100,f'Q,{BOOT}')
        self.assertEqual(state['fault'],'lease_lost')
        self.assertEqual(self.exchange(0x100+2999)['stage'],'YELLOW')
        self.assertEqual(self.exchange(0x100+3000)['stage'],'ALL_RED')
    def test_random_hostile_frames_never_produce_conflicting_outputs(self):
        rng=random.Random(2026)
        for i in range(1500):
            payload='X,'+''.join(rng.choice('0123456789abcdef,') for _ in range(rng.randrange(1,95)))
            result=self.exchange(i*10,payload)
            lamps=result['lamps']
            self.assertFalse(any(lamps[a]!='RED' for a in 'NS') and any(lamps[a]!='RED' for a in 'EW'))
            self.assertNotEqual(result['stage'],'GREEN')
    def test_corrupt_reply_and_gpio_mismatch_rejected(self):
        good=frame(f'R,{BOOT},1,1,0,0,12,2000')
        self.assertEqual(decode(good)['stage'],'GREEN')
        with self.assertRaises(ValueError):decode(good[:-3]+b'00\n')
        with self.assertRaises(ValueError):decode(frame(f'R,{BOOT},1,1,0,0,36,2000'))

    def test_malformed_command_fields_fail_closed_on_fresh_controller(self):
        payloads=[f'C,{BOOT},1,3,0,0,500',f'C,{BOOT},1,1,2,0,500',
                  f'C,{BOOT},1,1,0,0,501',f'C,{BOOT},4294967296,1,0,0,500',
                  f'C,{BOOT},1,1,0,0,500,extra',f'C,{BOOT},1,1,0,0,',
                  f'C,{BOOT},1,1,0,-1,500']
        for payload in payloads:
            with self.subTest(payload=payload):
                child=subprocess.Popen([self.executable],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
                try:
                    child.stdin.write(b'2000 1 1 '+frame(payload));child.stdin.flush()
                    state=decode(child.stdout.readline())
                    self.assertEqual((state['stage'],state['fault']),('ALL_RED','bad_frame'))
                finally:
                    child.stdin.close();child.wait(timeout=3);child.stdout.close()

    def test_measurements_scheduler_and_compiled_board_as_one_path(self):
        from sabz_edge.perception import RoadPlane,MetricProducer,Detection
        from sabz_edge.core import Observation
        from sabz_edge.runtime import Runtime
        from sabz_edge.store import Store
        calibration=lambda:RoadPlane([(0,0),(100,0),(100,200),(0,200)],[(0,200),(10,200),(10,0),(0,0)],width_m=10,length_m=200,uncertainty_m=1)
        producer=MetricProducer({a:calibration() for a in 'NSEW'})
        # Synthetic stationary tracks test fairness despite persistent heavy
        # demand. They are metadata fixtures, not a collision/vehicle model.
        detections=[Detection(i,'N',30+i%5*10,20+i*2,'car') for i in range(70)]
        detections.append(Detection(100,'E',50,198,'motorcycle'))
        stream=NativeStream(self.executable)
        adapter=SerialBenchAdapter(Timing(),stream=stream)
        clock=[0.0]
        runtime=Runtime(Store(':memory:'),clock=lambda:clock[0],wall=lambda:1000+clock[0])
        runtime.adapter=adapter
        held=yielded=fault_cleared=False
        try:
            for step in range(1401):
                t=step*.05;clock[0]=t;stream.now=round(t*1000)
                data=producer.update(detections,monotonic_now=t,captured_at=1000+t,
                     conflict_clear=True,downstream_counts=dict.fromkeys('NSEW',0),downstream_capacity=dict.fromkeys('NSEW',20),
                     sensors_healthy=not 54<=t<60)
                packet=dict(schema_version=3,sequence=step,counts=data['counts'],healthy=data['healthy'],
                     conflict_clear=data['conflict_clear'],captured_at=data['captured_at'],**data['traffic_state'],**data['approach_state'])
                runtime.submit('fixture',Observation.parse(packet,1000+t))
                output=runtime.tick();actual=adapter.readback
                self.assertIsNone(actual['fault'])
                held |= output['reason']=='allocated_green_complete'
                yielded |= actual['phase']=='EW' and actual['stage']=='GREEN'
                if 58<=t<60:fault_cleared |= actual['stage']=='ALL_RED'
            self.assertTrue(held,'Heavy queue never yielded at its bounded budget')
            self.assertTrue(yielded,'Waiting motorcycle was not served')
            self.assertTrue(fault_cleared,'Unhealthy sensing did not clear the compiled board')
        finally:runtime.close()

    def test_required_metric_fault_reaches_compiled_board_before_minimum(self):
        stream=NativeStream(self.executable)
        adapter=SerialBenchAdapter(Timing(require_metric_protection=True),stream=stream)
        try:
            adapter.apply({'command_sequence':1,'stage':'GREEN','phase':'NS','lease_s':.5,
                           'lamps':{'N':'GREEN','S':'GREEN','E':'RED','W':'RED'}})
            stream.now=2100
            adapter.apply({'command_sequence':2,'stage':'YELLOW','phase':'NS','lease_s':.5,
                           'reason':'metric_sensor_unavailable',
                           'lamps':{'N':'YELLOW','S':'YELLOW','E':'RED','W':'RED'}})
            self.assertEqual(adapter.readback['stage'],'YELLOW')
        finally:adapter.close()

    def test_python_adapter_to_compiled_firmware(self):
        stream=NativeStream(self.executable)
        adapter=SerialBenchAdapter(Timing(),stream=stream)
        try:
            adapter.apply({'command_sequence':1,'stage':'GREEN','phase':'NS','lease_s':.5,
                           'lamps':{'N':'GREEN','S':'GREEN','E':'RED','W':'RED'}})
            self.assertEqual(adapter.status()['stage'],'GREEN')
            self.assertEqual(adapter.readback['acknowledged_sequence'],1)
            self.assertFalse(adapter.readback['physical_lamp_verified'])
        finally:adapter.close()


class NativeStream:
    """Byte transport to compiled core; virtual device time advances explicitly."""
    def __init__(self,executable):
        self.process=subprocess.Popen([executable],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        self.now=2000;self.initial=True
    def read_until(self,*args):
        if self.initial:
            self.initial=False
            self.process.stdin.write(b'0 1 1 -\n');self.process.stdin.flush()
        return self.process.stdout.readline()
    def write(self,raw):
        self.process.stdin.write(f'{self.now} 1 1 '.encode()+raw);self.process.stdin.flush()
        self.now+=50
        return len(raw)
    def close(self):
        self.process.stdin.close();self.process.wait(timeout=3);self.process.stdout.close()

