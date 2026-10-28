"""Bounded shared-memory camera worker. Fault containment, not OS sandboxing.
No frames traverse pickle/queues or leave this host. Source is an explicit local
camera index. Host read-return timestamps do not prove exposure freshness.
"""
import multiprocessing
from multiprocessing import shared_memory
from math import isfinite
import time

MAX_WIDTH=1920
MAX_HEIGHT=1080
MAX_BYTES=MAX_WIDTH*MAX_HEIGHT*3


def capture_worker(source,name,metadata,lock,stop):
    # Import native decoder libraries in the worker, not the edge service.
    import cv2
    import numpy as np
    memory=shared_memory.SharedMemory(name=name)
    camera=None
    try:
        camera=cv2.VideoCapture(source)
        if not camera.isOpened():raise RuntimeError('Camera unavailable')
        camera.set(cv2.CAP_PROP_FRAME_WIDTH,MAX_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT,MAX_HEIGHT)
        sequence=0
        while not stop.is_set():
            ok,image=camera.read()
            mono,wall=time.monotonic(),time.time()
            if not ok:raise RuntimeError('Frame read failed')
            if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
                raise ValueError('Invalid capture format')
            height,width=image.shape[:2]
            if not (16<=width<=MAX_WIDTH and 16<=height<=MAX_HEIGHT):raise ValueError('Capture resolution exceeds bound')
            if not lock.acquire(timeout=.02):continue
            try:
                sequence+=1
                np.ndarray(image.shape,dtype=np.uint8,buffer=memory.buf)[:]=image
                metadata[:]=[sequence,mono,wall,width,height,1]
            finally:lock.release()
    except Exception:
        if lock.acquire(timeout=.02):
            try:metadata[5]=-1
            finally:lock.release()
    finally:
        if camera is not None:camera.release() # May block; parent owns termination.
        memory.close()


class ProcessCapture:
    def __init__(self,source,*,worker_target=capture_worker):
        if type(source) is not int or not 0<=source<=32:raise ValueError('Explicit local camera index 0..32 required')
        context=multiprocessing.get_context('spawn')
        self.memory=shared_memory.SharedMemory(create=True,size=MAX_BYTES)
        self.metadata=context.Array('d',6,lock=False)
        self.lock=context.Lock();self.stop=context.Event()
        self.closed=False;self.forced_termination=False
        self.process=context.Process(target=worker_target,args=(source,self.memory.name,self.metadata,self.lock,self.stop),name='sabz-camera-capture',daemon=True)
        try:self.process.start()
        except Exception:
            self.memory.close();self.memory.unlink();raise
    def take(self,previous_sequence,max_age=.15):
        if self.closed or not self.process.is_alive():return None
        if not self.lock.acquire(timeout=.02):return None
        try:
            sequence,mono,wall,width,height,status=self.metadata[:]
            if not all(isfinite(v) for v in (sequence,mono,wall,width,height,status)):return None
            if status!=1 or sequence<=previous_sequence or sequence!=int(sequence):return None
            if not 0<=time.monotonic()-mono<=max_age:return None
            if width!=int(width) or height!=int(height) or not (16<=width<=MAX_WIDTH and 16<=height<=MAX_HEIGHT):return None
            import numpy as np
            image=np.ndarray((int(height),int(width),3),dtype=np.uint8,buffer=self.memory.buf).copy()
            return int(sequence),mono,wall,image
        finally:self.lock.release()
    def close(self):
        if self.closed:return True
        self.stop.set();self.process.join(timeout=.4)
        if self.process.is_alive():
            self.forced_termination=True;self.process.terminate();self.process.join(timeout=1)
        if self.process.is_alive():self.process.kill();self.process.join(timeout=1)
        stopped=not self.process.is_alive()
        self.closed=True;self.memory.close();self.memory.unlink()
        return stopped
