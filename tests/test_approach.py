import unittest
from test_adaptive import packet
from sabz_edge.core import Controller, Observation, Timing


def metric(distance=50, speed=12):
    data = packet(counts=(1, 0, 70, 0))
    data.update(schema_version=3, nearest_moving_distance_m=dict.fromkeys('NSEW', None),
                max_approach_speed_mps=dict.fromkeys('NSEW', 0), distance_uncertainty_m=dict.fromkeys('NSEW', 1))
    data['nearest_moving_distance_m']['N'] = distance
    data['max_approach_speed_mps']['N'] = speed
    return Observation.parse(data, 1000)


class ApproachTests(unittest.TestCase):
    def controller(self):
        c = Controller(Timing(max_tick_gap=100), 0)
        c.tick(2, Observation.parse(packet(counts=(70, 0, 1, 0)), 1000), 2)
        return c

    def test_early_change_held_but_maximum_terminates(self):
        c = self.controller()
        self.assertEqual(c.tick(10, metric(), 10)['reason'], 'approach_protection_70m')
        self.assertEqual(c.tick(62, metric(), 62)['reason'], 'maximum_green')
        self.assertEqual(c.stage, 'YELLOW')
        self.assertEqual(c.tick(64, metric(), 64)['stage'], 'YELLOW')
        self.assertEqual(c.tick(65, metric(), 65)['stage'], 'ALL_RED')

    def test_slow_vehicle_does_not_hold(self):
        c = self.controller()
        self.assertEqual(c.tick(10, metric(70, 2.78), 10)['stage'], 'YELLOW')

    def test_expired_metrics_are_explicitly_unprotected(self):
        c = self.controller()
        state = c.tick(10, metric(), 9.7)
        self.assertEqual(state['approach_protection'], 'expired')
        self.assertEqual(state['stage'], 'YELLOW')

    def test_sensor_fault_still_clears(self):
        c = self.controller()
        c.trip('test_fault')
        self.assertEqual(c.tick(3, metric(), 3)['stage'], 'YELLOW')

    def test_small_cross_demand_gets_next_turn(self):
        data = packet(counts=(70, 0, 1, 0), waits=(1000, 0, 100, 0))
        obs = Observation.parse(data, 1000)
        c = Controller(Timing(max_tick_gap=100), 0)
        self.assertEqual(c.tick(2, obs, 2)['phase'], 'NS')
        c.tick(62, obs, 62)
        c.tick(65, obs, 65)
        state = c.tick(67, obs, 67)
        self.assertEqual((state['stage'], state['phase']), ('GREEN', 'EW'))

    def test_metric_validation(self):
        for distance, speed in ((float('nan'), 12), (-1, 12), (None, 12), (50, 0), (50, True)):
            with self.subTest(distance=distance, speed=speed), self.assertRaises(ValueError):
                metric(distance, speed)

