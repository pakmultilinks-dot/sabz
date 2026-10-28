import unittest
from sabz_edge.vision import Box
from sabz_edge.detection_eval import score_frame,metrics,acceptance,annotation,CLASSES

class DetectorEvaluationTests(unittest.TestCase):
    def test_duplicate_prediction_counts_as_false_positive(self):
        car=Box(0,0,10,10,.9,2)
        counts,error=score_frame([car],[car,car])
        self.assertEqual((counts[2]['tp'],counts[2]['fp'],counts[2]['fn']),(1,1,0))
        self.assertEqual(error,1)
    def test_wrong_vehicle_class_is_not_a_match(self):
        counts,error=score_frame([Box(0,0,10,10,1,3)],[Box(0,0,10,10,.9,2)])
        self.assertEqual(counts[3]['fn'],1);self.assertEqual(counts[2]['fp'],1)
    def test_person_misses_are_counted_separately(self):
        counts,error=score_frame([Box(0,0,10,10,1,0)],[])
        self.assertEqual(counts[0]['fn'],1);self.assertEqual(error,0)
    def test_missing_samples_cannot_pass_requirements(self):
        counts,_=score_frame([],[])
        req=dict(min_images=100,min_ground_truth_per_class=10,min_precision=dict.fromkeys(CLASSES.values(),.9),min_recall=dict.fromkeys(CLASSES.values(),.9))
        report=acceptance(metrics(counts),0,req)
        self.assertFalse(report['requirements_met']);self.assertFalse(report['commercial_ready'])
    def test_dataset_pass_does_not_authorize_commercial_release(self):
        counts={k:dict(tp=10,fp=0,fn=0,ground_truth=10) for k in CLASSES}
        req=dict(min_images=10,min_ground_truth_per_class=10,min_precision=dict.fromkeys(CLASSES.values(),.9),min_recall=dict.fromkeys(CLASSES.values(),.9))
        report=acceptance(metrics(counts),10,req)
        self.assertTrue(report['requirements_met']);self.assertFalse(report['commercial_ready'])
    def test_invalid_annotations_rejected(self):
        for item in ({'class_id':True,'bbox':[0,0,1,1]},{'class_id':2,'bbox':[5,5,1,1]},{'class_id':2,'bbox':[0,0,float('nan'),1]}):
            with self.assertRaises(ValueError):annotation(item)
