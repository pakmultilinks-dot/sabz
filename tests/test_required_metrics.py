"""Required metric inputs must fail closed throughout the command path."""
import unittest
from sabz_edge.core import Controller,Timing,Observation
from sabz_edge.runtime import Runtime
from sabz_edge.store import Store
from sabz_edge.cabinet_model import Guard
from test_approach import metric
from test_edge import payload

class RequiredMetricTests(unittest.TestCase):
    def test_missing_metric_input_cannot_start_green(self):
        c=Controller(Timing(max_tick_gap=10,require_metric_protection=True),0)
        result=c.tick(2,Observation.parse(payload(),1000),2)
        self.assertEqual(result['stage'],'ALL_RED')
        self.assertEqual(result['reason'],'metric_sensor_unavailable')
    def test_expired_metrics_terminate_before_minimum_but_keep_clearance(self):
        c=Controller(Timing(max_tick_gap=10,require_metric_protection=True),0)
        self.assertEqual(c.tick(2,metric(),2)['stage'],'GREEN')
        result=c.tick(2.21,metric(),2)
        self.assertEqual((result['stage'],result['reason']),('YELLOW','metric_sensor_unavailable'))
        self.assertEqual(c.tick(5.2,metric(),5.2)['stage'],'YELLOW')
        self.assertEqual(c.tick(5.21,metric(),5.21)['stage'],'ALL_RED')
        self.assertEqual(c.tick(7.3,metric(),7.3)['stage'],'GREEN')
    def test_independent_guard_accepts_metric_fault_before_minimum(self):
        guard=Guard(Timing(),0)
        def command(seq,stage,reason='normal'):
            lamps={'N':stage if stage!='ALL_RED' else 'RED','S':stage if stage!='ALL_RED' else 'RED','E':'RED','W':'RED'}
            return dict(command_sequence=seq,lease_s=.5,stage=stage,phase='NS',reason=reason,lamps=lamps)
        self.assertEqual(guard.accept(command(1,'GREEN'),2)['stage'],'GREEN')
        self.assertEqual(guard.accept(command(2,'YELLOW','metric_sensor_unavailable'),2.1)['stage'],'YELLOW')
    def test_slow_audit_cannot_issue_green_with_expired_metric_data(self):
        clock=[0.0];store=Store(':memory:')
        runtime=Runtime(store,Timing(max_tick_gap=10,require_metric_protection=True),clock=lambda:clock[0],wall=lambda:1000)
        runtime.tick();clock[0]=2;runtime.submit('sensor',metric())
        original=store.event
        def delayed(*args):original(*args);clock[0]+=.3
        store.event=delayed
        try:
            with self.assertRaises(RuntimeError):runtime.tick()
            self.assertEqual(runtime.adapter.last['stage'],'ALL_RED')
            self.assertFalse(runtime.status()['ready'])
        finally:runtime.close()
    def test_configuration_does_not_accept_truthy_strings(self):
        for value in ('false',1,None):
            with self.assertRaises(ValueError):Timing(require_metric_protection=value)
