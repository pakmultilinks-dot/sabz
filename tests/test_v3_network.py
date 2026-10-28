"""Schema-3 approach protection through HTTP and independent cabinet readback."""
from pathlib import Path
import tempfile
import threading
import time
import unittest
from sabz_edge.client import CameraClient
from sabz_edge.core import Timing
from sabz_edge.guard import CabinetAdapter
from sabz_edge.runtime import Runtime
from sabz_edge.server import Server,Settings
from sabz_edge.store import Store

class MetricIntegrationTests(unittest.TestCase):
    def test_fast_approach_is_bounded_then_cross_demand_gets_green(self):
        with tempfile.TemporaryDirectory() as directory:
            timing=Timing(min_green=.3,max_green=2.5,yellow=.3,all_red=.2)
            adapter=CabinetAdapter(timing)
            runtime=Runtime(Store(':memory:'),timing)
            runtime.adapter=adapter
            settings=Settings({'SABZ_CAMERA_TOKEN':'c'*32,'SABZ_READER_TOKEN':'r'*32,'SABZ_PORT':'0'})
            server=Server(settings,runtime)
            runtime.start()
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
            client=CameraClient(f'http://127.0.0.1:{server.server_port}','c'*32,str(Path(directory)/'sender.db'))
            traffic={k:dict.fromkeys('NSEW',v) for k,v in [('downstream_counts',0),('downstream_capacity',20),('approaching',0),('arrival_rate',0),('oldest_wait_s',0)]}
            metrics={'nearest_moving_distance_m':dict(zip('NSEW',(50,None,None,None))),
                     'max_approach_speed_mps':dict(zip('NSEW',(12,0,0,0))),'distance_uncertainty_m':dict.fromkeys('NSEW',1)}
            start=time.monotonic();seen=[]
            try:
                while time.monotonic()-start<4.5:
                    elapsed=time.monotonic()-start
                    counts=dict(zip('NSEW',(70,0,1,0) if elapsed<.6 else (1,0,70,0)))
                    accepted=client.send(counts,conflict_clear=True,traffic_state=traffic,approach_state=metrics)
                    data=runtime.status();actual=data['cabinet_readback']
                    self.assertFalse(actual['fault'])
                    self.assertFalse(actual['lamps']['N']=='GREEN' and actual['lamps']['E']=='GREEN')
                    seen.append((data['last_output'],actual))
                    time.sleep(.1)
                self.assertTrue(any(out['reason']=='approach_protection_70m' and act['phase']=='NS' and act['stage']=='GREEN' for out,act in seen))
                self.assertTrue(any(out['reason']=='maximum_green' for out,act in seen))
                self.assertTrue(any(act['phase']=='EW' and act['stage']=='GREEN' for out,act in seen))
                self.assertTrue(any(out.get('observation_sequence') is not None for out,act in seen))
            finally:
                client.close();server.shutdown();server.server_close();thread.join();runtime.close()
