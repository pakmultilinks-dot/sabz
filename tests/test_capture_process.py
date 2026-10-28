"""No physical device opened: workers below write synthetic shared-memory frames."""
import time
import unittest
from multiprocessing import shared_memory
from sabz_edge.capture import ProcessCapture


def stuck_worker(source,name,metadata,lock,stop):
    memory=shared_memory.SharedMemory(name=name)
    try:
        memory.buf[:16*16*3]=bytes([17])*(16*16*3)
        with lock:metadata[:]=[1,time.monotonic(),time.time(),16,16,1]
        time.sleep(3600) # Deliberately ignores the shutdown event.
    finally:memory.close()


def corrupt_worker(source,name,metadata,lock,stop):
    with lock:metadata[:]=[1,time.monotonic(),time.time(),999999999,16,1]
    stop.wait(5)


def wait_metadata(camera):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if camera.lock.acquire(timeout=.02):
            try:
                if camera.metadata[5]!=0:return
            finally:camera.lock.release()
        time.sleep(.01)
    raise AssertionError('Capture fixture did not start')

class ProcessCaptureTests(unittest.TestCase):
    def test_stuck_worker_can_be_terminated_without_blocking_parent(self):
        camera=ProcessCapture(0,worker_target=stuck_worker)
        wait_metadata(camera)
        started=time.monotonic()
        try:
            self.assertTrue(camera.close())
            self.assertTrue(camera.forced_termination)
            self.assertFalse(camera.process.is_alive())
            self.assertLess(time.monotonic()-started,3)
        finally:camera.close()
    def test_corrupt_dimensions_rejected_before_copy(self):
        camera=ProcessCapture(0,worker_target=corrupt_worker)
        try:
            wait_metadata(camera)
            self.assertIsNone(camera.take(0,max_age=3))
        finally:self.assertTrue(camera.close())
    def test_frame_is_copied_and_then_expires(self):
        try:import numpy
        except ImportError:self.skipTest('Optional NumPy unavailable')
        camera=ProcessCapture(0,worker_target=stuck_worker)
        try:
            wait_metadata(camera)
            result=camera.take(0,max_age=3)
            self.assertIsNotNone(result)
            self.assertEqual(result[3].shape,(16,16,3))
            self.assertEqual(int(result[3][0,0,0]),17)
            self.assertIsNone(camera.take(result[0]))
            from unittest.mock import patch
            with patch('sabz_edge.capture.time.monotonic',return_value=result[1]+.3):
                self.assertIsNone(camera.take(0))
        finally:self.assertTrue(camera.close())
    def test_network_sources_and_implicit_devices_are_rejected(self):
        for source in ('rtsp://example',None,True,-1,33):
            with self.assertRaises(ValueError):ProcessCapture(source)
