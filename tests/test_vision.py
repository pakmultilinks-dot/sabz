import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from sabz_edge.vision import Box,RoadTracker,YoloOnnx,overlap
from sabz_edge.camera_sensor import independent_state
from sabz_edge.perception import RoadPlane
try:import numpy as np
except ImportError:np=None


def planes():
    return {a:RoadPlane([(i*200,0),(i*200+100,0),(i*200+100,200),(i*200,200)],[(0,200),(10,200),(10,0),(0,0)],width_m=10,length_m=200,uncertainty_m=1)
            for i,a in enumerate('NSEW')}

class CameraContractTests(unittest.TestCase):
    def test_tracker_identity_is_unique_and_expires(self):
        tracker=RoadTracker(planes())
        boxes=[Box(40,100,60,130,.9,2),Box(70,100,80,130,.8,2)]
        tracks,_=tracker.update(boxes,1)
        self.assertNotEqual(tracks[0].track_id,tracks[1].track_id)
        ids=[t.track_id for t in tracks]
        followed,_=tracker.update(boxes,1.1)
        self.assertEqual([t.track_id for t in followed],ids)
        self.assertNotIn(tracker.update(boxes,2)[0][0].track_id,ids)
    def test_approach_regions_and_person_handling(self):
        tracker=RoadTracker(planes())
        tracks,_=tracker.update([Box(440,100,460,130,.9,3)],1)
        self.assertEqual(tracks[0].approach,'E')
        tracks,pedestrians=tracker.update([Box(40,100,60,130,.9,0)],1.1)
        self.assertEqual(tracks,[])
        self.assertEqual(pedestrians,{'N':1,'S':0,'E':0,'W':0})
    def test_overlapping_regions_are_not_silently_assigned(self):
        calibration=planes()['N'];tracker=RoadTracker(dict.fromkeys('NSEW',calibration))
        with self.assertRaises(ValueError):tracker.update([Box(40,100,60,130,.9,2)],1)
    def test_model_hash_rejected_before_parsing(self):
        try:import cv2
        except ImportError:self.skipTest('Optional OpenCV unavailable')
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'untrusted.onnx';path.write_bytes(b'not a model')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):YoloOnnx(path,'0'*64)
    def test_fresh_independent_sensor_contract(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'state.json'
            state=dict(captured_at=1000,healthy=True,conflict_clear=False,downstream_counts=dict.fromkeys('NSEW',0),downstream_capacity=dict.fromkeys('NSEW',20))
            path.write_text(json.dumps(state),encoding='utf-8')
            self.assertFalse(independent_state(path,1000.1)['conflict_clear'])
            with self.assertRaises(ValueError):independent_state(path,1000.2)
            with self.assertRaises(ValueError):independent_state(path,999)
    def test_overlap_is_bounded(self):
        a=Box(0,0,10,10,.9,2)
        self.assertEqual(overlap(a,a),1)
        self.assertEqual(overlap(a,Box(20,20,30,30,.8,2)),0)

@unittest.skipIf(np is None,'Optional NumPy unavailable; detector tensor tests require vision extra')
class DetectorTensorTests(unittest.TestCase):
    def test_all_supported_vehicle_classes_survive_overlap(self):
        from sabz_edge.vision import decode_yolo,VEHICLES
        output=np.zeros((1,84,len(VEHICLES)),dtype=np.float32)
        for i,cls in enumerate(VEHICLES):
            output[0,:4,i]=[320,320,100,100]
            output[0,4+cls,i]=.9
        boxes=decode_yolo(output,image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0)
        self.assertEqual({b.class_id for b in boxes},set(VEHICLES))

    def test_dense_nonoverlapping_motorcycles_are_not_lost(self):
        from sabz_edge.vision import decode_yolo
        output=np.zeros((1,84,100),dtype=np.float32)
        for i in range(100):
            output[0,:4,i]=[20+(i%10)*60,20+(i//10)*60,12,20]
            output[0,7,i]=.9
        boxes=decode_yolo(output,image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0)
        self.assertEqual(len(boxes),100)

    def test_empty_low_confidence_and_outside_image(self):
        from sabz_edge.vision import decode_yolo
        output=np.zeros((1,84,3),dtype=np.float32)
        output[0,:4,:]=np.array([[50,-100,50],[50,-100,50],[20,10,20],[20,10,20]])
        output[0,6,:]=[.1,.9,.2]
        self.assertEqual(decode_yolo(output,image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0),[])

    def test_candidate_overflow_and_invalid_geometry(self):
        from sabz_edge.vision import decode_yolo
        output=np.zeros((1,84,2001),dtype=np.float32);output[0,6,:]=.9
        with self.assertRaisesRegex(ValueError,'Excessive'):decode_yolo(output,image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0)
        for geometry in ([50,50,0,10],[50,50,-10,10],[1e6,50,10,10]):
            output=np.zeros((1,84,1),dtype=np.float32);output[0,:4,0]=geometry;output[0,6,0]=.9
            with self.assertRaises(ValueError):decode_yolo(output,image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0)

    def test_invalid_preprocessing_parameters_rejected(self):
        from sabz_edge.vision import decode_yolo
        defaults=dict(image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0)
        for key,value in [('scale',0),('scale',float('nan')),('image_width',True),('image_height',0),('pad_x',-1),('threshold',float('nan'))]:
            with self.subTest(key=key,value=value):
                with self.assertRaises(ValueError):decode_yolo(np.zeros((1,84,1),dtype=np.float32),**{**defaults,key:value})

    def test_coco_output_letterbox_and_duplicate_suppression(self):
        from sabz_edge.vision import decode_yolo
        output=np.zeros((1,84,2),dtype=np.float32)
        output[0,:4,:]=np.array([[320,320],[320,320],[100,100],[100,100]])
        output[0,6,0]=.9;output[0,6,1]=.8
        boxes=decode_yolo(output,image_width=1280,image_height=720,scale=.5,pad_x=0,pad_y=140)
        self.assertEqual(len(boxes),1)
        self.assertEqual(boxes[0].class_id,2)
        self.assertAlmostEqual(boxes[0].foot[0],640)
        self.assertAlmostEqual(boxes[0].y2,460)
    def test_image_preprocessing_to_tracker_and_metric_measurements(self):
        try:import cv2
        except ImportError:self.skipTest('Optional OpenCV unavailable')
        from sabz_edge.perception import MetricProducer
        class Net:
            y=252.0
            def setInput(self,blob):
                if blob.shape!=(1,3,640,640):raise AssertionError('Wrong network input shape')
            def forward(self):
                output=np.zeros((1,84,1),dtype=np.float32)
                output[0,:4,0]=[40,self.y,16,24]
                output[0,6,0]=.9
                return output
        # The network output is a fixture, not a trained image detector.
        detector=YoloOnnx.__new__(YoloOnnx);detector.net=Net()
        tracker=RoadTracker(planes());producer=MetricProducer(planes())
        image=np.zeros((400,800,3),dtype=np.uint8)
        common=dict(conflict_clear=False,downstream_counts=dict.fromkeys('NSEW',0),
                    downstream_capacity=dict.fromkeys('NSEW',20),sensors_healthy=True)
        producer.update(tracker.update(detector.detect(image),1)[0],monotonic_now=1,captured_at=1001,**common)
        detector.net.y+=.96 # 1.2 pixels on the original road image in 0.1 s.
        data=producer.update(tracker.update(detector.detect(image),1.1)[0],monotonic_now=1.1,captured_at=1001.1,**common)
        self.assertTrue(data['healthy'])
        self.assertAlmostEqual(data['approach_state']['max_approach_speed_mps']['N'],12,places=2)
        self.assertFalse(data['conflict_clear'])

    def test_vehicle_suppression_does_not_hide_overlapping_person(self):
        from sabz_edge.vision import decode_yolo
        output=np.zeros((1,84,2),dtype=np.float32)
        output[0,:4,:]=np.array([[50,50],[115,115],[20,20],[30,30]])
        output[0,6,0]=.9;output[0,4,1]=.8
        boxes=decode_yolo(output,image_width=800,image_height=400,scale=1,pad_x=0,pad_y=0)
        self.assertEqual(len(boxes),2)
        tracks,pedestrians=RoadTracker(planes()).update(boxes,1)
        self.assertEqual(len(tracks),1)
        self.assertEqual(sum(pedestrians.values()),1)

    def test_bad_output_shape_nan_and_probabilities_rejected(self):
        from sabz_edge.vision import decode_yolo
        bad=[np.zeros((1,85,10)),np.full((1,84,1),float('nan')),np.ones((1,84,1))*2]
        for tensor in bad:
            with self.assertRaises(ValueError):decode_yolo(tensor,image_width=640,image_height=640,scale=1,pad_x=0,pad_y=0)
