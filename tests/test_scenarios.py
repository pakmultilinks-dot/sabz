import unittest
from sabz_edge.scenario_matrix import Case,run_case
from sabz_edge.core import Observation

class QueueScenarioTests(unittest.TestCase):
    def test_single_vehicle_clears(self):
        result=run_case(Case('one',(1,0,0,0),duration=30))
        self.assertTrue(result['passed'],result['violations'])
        self.assertEqual(result['served'],[1,0,0,0])
    def test_heavy_queue_yields_before_it_empties(self):
        result=run_case(Case('heavy',(50,1,1,1),duration=120))
        self.assertTrue(result['passed'],result['violations'])
        cross=next(t for t in result['transitions'] if t['stage']=='GREEN' and t['phase']=='EW')
        self.assertGreater(cross['queues'][0],0)
        self.assertLessEqual(result['first_service_s'][2],60)
    def test_old_queues_do_not_destroy_equal_demand_batching(self):
        result=run_case(Case('equal',(100,100,100,100),duration=300))
        self.assertTrue(result['passed'],result['violations'])
        self.assertGreater(sum(result['served']),250)
        self.assertTrue(all(g['duration_s']>=40 for g in result['green_intervals'][:4]))
    def test_fifth_approach_is_rejected_not_silently_mapped(self):
        packet=dict(schema_version=1,sequence=1,captured_at=1000,counts=dict.fromkeys(('N','S','E','W','F'),1),healthy=True,conflict_clear=True)
        with self.assertRaises(ValueError):Observation.parse(packet,1000)
