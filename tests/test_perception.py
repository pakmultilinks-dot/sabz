import unittest
from dataclasses import replace
from sabz_edge.perception import RoadPlane,MetricProducer,Detection
from sabz_edge.core import Observation,Controller,Timing
from test_adaptive import packet,obs
from sabz_edge.adaptive import AdaptivePolicy


def calibration():
    return RoadPlane([(0,0),(100,0),(100,200),(0,200)],[(0,200),(10,200),(10,0),(0,0)],width_m=10,length_m=200,uncertainty_m=1)

class PerceptionTests(unittest.TestCase):
    def setUp(self):self.producer=MetricProducer({a:calibration() for a in 'NSEW'})
    def update(self,now,detections,**kw):
        defaults=dict(monotonic_now=now,captured_at=1000+now,conflict_clear=False,
                      downstream_counts=dict.fromkeys('NSEW',0),downstream_capacity=dict.fromkeys('NSEW',20),sensors_healthy=True)
        defaults.update(kw)
        return self.producer.update(detections,**defaults)
    def test_survey_projection_and_degenerate_rejection(self):
        x,d=calibration().project(50,130)
        self.assertAlmostEqual(x,5);self.assertAlmostEqual(d,70)
        with self.assertRaises(ValueError):RoadPlane([(0,0)]*4,[(0,0)]*4,width_m=10,length_m=200,uncertainty_m=1)
        with self.assertRaises(ValueError):calibration().project(101,100)
    def test_speed_queue_motorcycle_and_privacy(self):
        first=[Detection(1,'N',50,130,'car'),Detection(2,'E',50,198,'motorcycle')]
        self.assertFalse(self.update(1,first)['healthy'])
        data=self.update(1.1,[replace(first[0],pixel_y=131.2),first[1]])
        self.assertTrue(data['healthy'])
        self.assertAlmostEqual(data['approach_state']['max_approach_speed_mps']['N'],12)
        self.assertEqual(data['counts']['E'],1)
        self.assertFalse(data['conflict_clear'])
        self.assertNotIn('track_id',str(data));self.assertNotIn('pixel_',str(data))
        for i in range(2,12):data=self.update(1+i*.1,[replace(first[0],pixel_y=130+i*1.2),first[1]])
        self.assertGreater(data['traffic_state']['oldest_wait_s']['E'],.9)
    def test_new_track_uses_conservative_speed_without_stopping_every_arrival(self):
        self.update(1,[])
        data=self.update(1.1,[Detection(10,'N',50,150,'car')])
        self.assertTrue(data['healthy'])
        self.assertEqual(data['approach_state']['max_approach_speed_mps']['N'],70)
    def test_missing_track_and_stale_frame_are_unhealthy(self):
        detection=Detection(1,'N',50,130,'car')
        self.update(1,[detection])
        self.assertFalse(self.update(1.1,[])['healthy'])
        self.assertFalse(self.update(2,[detection])['healthy'])
        with self.assertRaises(ValueError):self.update(2,[detection])
    def test_no_clearance_inference_and_arrivals_not_queue_deltas(self):
        self.update(1,[])
        data=self.update(1.1,[])
        self.assertTrue(data['healthy']);self.assertFalse(data['conflict_clear'])
        d=Detection(1,'N',50,150,'car')
        self.update(1.2,[d]);data=self.update(1.3,[d])
        self.assertEqual(data['traffic_state']['arrival_rate']['N'],0)
    def test_arrival_rate_measures_upstream_line_crossing_once(self):
        d=Detection(1,'N',50,39,'car')
        self.update(1,[d])
        data=self.update(1.1,[replace(d,pixel_y=41)])
        self.assertAlmostEqual(data['traffic_state']['arrival_rate']['N'],1/30)
        data=self.update(1.2,[replace(d,pixel_y=43)])
        self.assertAlmostEqual(data['traffic_state']['arrival_rate']['N'],1/30)

    def test_duplicate_or_unsupported_detection_rejected(self):
        d=Detection(1,'N',50,150,'car')
        for items in ([d,d],[replace(d,vehicle_class='dog')],[replace(d,pixel_y=float('nan'))]):
            with self.assertRaises(ValueError):self.update(1,items)
    def test_person_detections_tally_as_pedestrians_not_vehicles(self):
        d=Detection(1,'N',50,150,'person')
        data=self.update(1,[d])
        self.assertEqual(data['counts']['N'],0)
        self.assertEqual(data['pedestrian_queue']['N'],1)
        with self.assertRaises(ValueError):self.update(1.1,[d],pedestrian_queue=dict.fromkeys('NSEW',0))
    def test_pedestrian_queue_validation_and_v4_round_trip(self):
        with self.assertRaises(ValueError):self.update(1,[],pedestrian_queue={'N':1})
        with self.assertRaises(ValueError):self.update(1,[],pedestrian_queue={'N':-1,'S':0,'E':0,'W':0})
        with self.assertRaises(ValueError):self.update(1,[],pedestrian_queue={'N':1.5,'S':0,'E':0,'W':0})
        with self.assertRaises(ValueError):self.update(1,[],pedestrian_queue={'N':True,'S':0,'E':0,'W':0})
        self.update(0.9,[])  # warm-up frame: healthy requires a prior frame
        data=self.update(1,[],pedestrian_queue={'N':7,'S':0,'E':2,'W':0})
        self.assertTrue(data['healthy'])
        self.assertEqual(data['pedestrian_queue'],{'N':7,'S':0,'E':2,'W':0})
        packet=dict(schema_version=4,sequence=1,counts=data['counts'],captured_at=data['captured_at'],
                    healthy=data['healthy'],conflict_clear=False,**data['traffic_state'],
                    **data['approach_state'],pedestrian_queue=data['pedestrian_queue'])
        observation=Observation.parse(packet,1001)
        self.assertEqual(observation.pedestrian_queue,(7,0,2,0))
        self.assertEqual(observation.schema_version,4)
        # v3 packets without pedestrian_queue remain valid.
        packet.pop('pedestrian_queue');packet['schema_version']=3
        self.assertEqual(Observation.parse(packet,1001).pedestrian_queue,())
    def test_aggregates_feed_real_schema_and_control_kernel(self):
        d=Detection(1,'N',50,150,'car')
        self.update(1,[d]);data=self.update(1.1,[replace(d,pixel_y=151.2)],conflict_clear=True)
        packet=dict(schema_version=3,sequence=1,counts=data['counts'],captured_at=data['captured_at'],healthy=data['healthy'],conflict_clear=data['conflict_clear'],**data['traffic_state'],**data['approach_state'])
        observation=Observation.parse(packet,1001.1)
        controller=Controller(Timing(max_tick_gap=10),0)
        state=controller.tick(2,observation,2)
        self.assertEqual(state['stage'],'GREEN')
        self.assertEqual(state['algorithm'],'capacity-aware-adaptive-v1')
    def test_250_vehicle_queue_is_not_clipped_in_metric_path(self):
        vehicles=[Detection(i,'N',30+i%5*10,100,'car') for i in range(250)]
        self.update(1,vehicles)
        data=self.update(1.1,vehicles)
        self.assertTrue(data['healthy'])
        self.assertEqual(data['counts']['N'],250)
        packet=dict(schema_version=3,sequence=1,captured_at=data['captured_at'],counts=data['counts'],
                    healthy=data['healthy'],conflict_clear=False,**data['traffic_state'],**data['approach_state'])
        self.assertEqual(Observation.parse(packet,1001.1).counts[0],250)
        packet['counts']['N']=501
        with self.assertRaises(ValueError):Observation.parse(packet,1001.1)

    def test_one_blocked_member_blocks_shared_phase(self):
        policy=AdaptivePolicy()
        policy.inspect(obs(counts=(70,0,1,0),downstream=(20,0,0,0)),0)
        self.assertFalse(policy.details['NS']['supply_available'])
        self.assertEqual(policy.next_phase('NS'),'EW')
    def test_blocked_current_phase_terminates_even_if_other_is_blocked(self):
        policy=AdaptivePolicy()
        policy.inspect(obs(downstream=(20,20,20,20)),0)
        self.assertEqual(policy.switch_reason('NS','EW',0,10),'downstream_blocked')

    def test_large_queue_uses_bounded_budget_then_serves_bike(self):
        policy=AdaptivePolicy();policy.inspect(obs(counts=(70,0,1,0)),0)
        self.assertEqual(policy.details['NS']['target_green_s'],45)
        self.assertIsNone(policy.switch_reason('NS','EW',0,44))
        self.assertEqual(policy.switch_reason('NS','EW',0,45),'allocated_green_complete')


class PerceptionHTTPTests(unittest.TestCase):
    import test_edge as fixtures
    setUp=fixtures.HTTPTests.setUp
    tearDown=fixtures.HTTPTests.tearDown
    request=fixtures.HTTPTests.request

    def test_calibrated_aggregates_reach_api_policy_and_minimized_audit(self):
        import json,time
        from sabz_edge.sensor_ingest import process_frame
        producer=MetricProducer({a:calibration() for a in 'NSEW'})
        frame=dict(frame_time_s=1,captured_at=time.time(),conflict_clear=False,
                   downstream_counts=dict.fromkeys('NSEW',0),downstream_capacity=dict.fromkeys('NSEW',20),sensors_healthy=True,
                   detections=[dict(track_id=1,approach='N',pixel_x=50,pixel_y=130,vehicle_class='car'),
                               dict(track_id=2,approach='E',pixel_x=50,pixel_y=198,vehicle_class='motorcycle')])
        process_frame(producer,frame)
        frame['frame_time_s']=1.1;frame['detections'][0]['pixel_y']=131.2
        frame['captured_at']=time.time()
        aggregate=process_frame(producer,frame)
        payload=dict(schema_version=3,sequence=1,captured_at=aggregate['captured_at'],
                     counts=aggregate['counts'],healthy=aggregate['healthy'],conflict_clear=aggregate['conflict_clear'],
                     **aggregate['traffic_state'],**aggregate['approach_state'])
        self.assertEqual(self.request('POST','/v1/observations',payload,'c'*32)[0],202)
        time.sleep(.06)
        _,status=self.request('GET','/v1/status',token='r'*32)
        self.assertEqual(status['controller']['algorithm'],'capacity-aware-adaptive-v1')
        self.assertEqual(status['controller']['phase_scores']['EW']['present'],1)
        self.assertEqual(status['controller']['stage'],'ALL_RED')
        audit=self.store.db.execute("SELECT payload FROM events WHERE kind='observation'").fetchone()[0]
        self.assertNotIn('track_id',audit);self.assertNotIn('pixel_',audit)
        self.assertNotIn('nearest_moving_distance_m',audit)


class SenderDurabilityTests(unittest.TestCase):
    def test_contended_sequence_store_fails_before_network_submission(self):
        import tempfile,sqlite3,time
        from pathlib import Path
        from sabz_edge.client import CameraClient
        with tempfile.TemporaryDirectory() as root:
            path=str(Path(root)/'sequence.db')
            sender=CameraClient('http://127.0.0.1:1','c'*32,path)
            blocker=sqlite3.connect(path)
            try:
                self.assertEqual(sender.db.execute('PRAGMA journal_mode').fetchone()[0],'wal')
                blocker.execute('BEGIN IMMEDIATE')
                started=time.monotonic()
                with self.assertRaises(sqlite3.OperationalError):sender.send(dict.fromkeys('NSEW',0))
                self.assertLess(time.monotonic()-started,1)
                self.assertIsNone(sender.last_timings)
            finally:
                blocker.rollback();blocker.close();sender.close()
