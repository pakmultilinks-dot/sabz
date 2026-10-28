"""Local calibrated detections -> aggregate observation v3. No frames/IDs emitted.
Surveyed planar geometry only; calibration accuracy must be measured on site.
Conflict clearance and receiving-road occupancy require independent inputs.
"""
from collections import deque
from dataclasses import dataclass
from math import isfinite
from .core import APPROACHES,number


def solve(matrix):
    a=[list(row) for row in matrix]
    n=len(a)
    for col in range(n):
        pivot=max(range(col,n),key=lambda i:abs(a[i][col]))
        if abs(a[pivot][col])<1e-10:raise ValueError('Degenerate calibration points')
        a[col],a[pivot]=a[pivot],a[col]
        scale=a[col][col];a[col]=[v/scale for v in a[col]]
        for row in range(n):
            if row!=col:
                scale=a[row][col]
                a[row]=[v-scale*w for v,w in zip(a[row],a[col])]
    return tuple(row[-1] for row in a)


class RoadPlane:
    def __init__(self,pixel_points,road_points,*,width_m,length_m,uncertainty_m):
        self.width=number(width_m,'road width',.5,50)
        self.length=number(length_m,'surveyed length',1,500)
        self.uncertainty=number(uncertainty_m,'distance uncertainty',0,20)
        if len(pixel_points)!=4 or len(road_points)!=4:raise ValueError('Four surveyed point pairs required')
        matrix=[]
        for pixel,road in zip(pixel_points,road_points):
            if len(pixel)!=2 or len(road)!=2:raise ValueError('Expected two-dimensional point pairs')
            u,v=(number(p,'pixel coordinate',0,100000) for p in pixel)
            x,y=(number(p,'road coordinate',-500,500) for p in road)
            matrix.extend(([u,v,1,0,0,0,-x*u,-x*v,x],[0,0,0,u,v,1,-y*u,-y*v,y]))
        self.h=solve(matrix)
        a,b,c,d,e,f,g,h=self.h
        determinant=a*(e-f*h)-b*(d-f*g)+c*(d*h-e*g)
        if not isfinite(determinant) or abs(determinant)<1e-10:raise ValueError('Singular road-plane mapping')
    def project(self,u,v):
        u=number(u,'pixel x',0,100000);v=number(v,'pixel y',0,100000)
        a,b,c,d,e,f,g,h=self.h
        denominator=g*u+h*v+1
        if abs(denominator)<1e-8:raise ValueError('Point at projection horizon')
        x,y=(a*u+b*v+c)/denominator,(d*u+e*v+f)/denominator
        if not isfinite(x+y):raise ValueError('Invalid projected point')
        if not 0<=x<=self.width or not -5<=y<=self.length:
            raise ValueError('Detection outside surveyed road region')
        return x,y


@dataclass(frozen=True)
class Detection:
    track_id: int  # temporary detector track only, not a person/plate identity
    approach: str
    pixel_x: float
    pixel_y: float
    vehicle_class: str


class MetricProducer:
    ttl_s=2.0
    def __init__(self,calibrations):
        if set(calibrations)!=set(APPROACHES) or not all(isinstance(c,RoadPlane) for c in calibrations.values()):
            raise ValueError('Calibrations for exactly N/S/E/W required')
        self.calibrations=calibrations
        self.tracks={};self.arrivals={a:deque() for a in APPROACHES};self.last_frame=None
    def update(self,detections,*,monotonic_now,captured_at,conflict_clear,downstream_counts,downstream_capacity,sensors_healthy):
        now=number(monotonic_now,'monotonic frame time',0,1e12)
        number(captured_at,'capture timestamp',0,1e12)
        if any(type(v) is not bool for v in (conflict_clear,sensors_healthy)):raise ValueError('Sensor health/clearance must be booleans')
        if self.last_frame is not None and now<=self.last_frame:raise ValueError('Frame time must strictly increase')
        if not isinstance(detections,(list,tuple)) or len(detections)>2000:raise ValueError('At most 2000 detections per frame')
        for mapping in (downstream_counts,downstream_capacity):
            if not isinstance(mapping,dict) or set(mapping)!=set(APPROACHES):raise ValueError('Independent downstream maps required')
        for a in APPROACHES:
            cap=number(downstream_capacity[a],'capacity',1,500)
            number(downstream_counts[a],'receiving count',0,cap)
        # Validate/project the complete frame before changing state.
        projected=[];seen=set()
        for det in detections:
            if not isinstance(det,Detection) or type(det.track_id) is not int or not 0<=det.track_id<2**63 or det.approach not in APPROACHES:
                raise ValueError('Invalid ephemeral detection')
            if det.vehicle_class not in ('car','motorcycle','bicycle','bus','truck'):raise ValueError('Unsupported road user; this release has no pedestrian controller')
            key=(det.approach,det.track_id)
            if key in seen:raise ValueError('Duplicate track in frame')
            seen.add(key)
            x,distance=self.calibrations[det.approach].project(det.pixel_x,det.pixel_y)
            projected.append((key,x,distance))
        # Expire tracks on elapsed time, not frame count. No persistence/network IDs.
        self.tracks={k:v for k,v in self.tracks.items() if now-v['at']<=self.ttl_s}
        healthy=sensors_healthy and self.last_frame is not None and now-self.last_frame<=.2
        if any(k not in seen and v['distance']>=0 for k,v in self.tracks.items()):healthy=False
        counts=dict.fromkeys(APPROACHES,0);approaching=dict.fromkeys(APPROACHES,0)
        nearest=dict.fromkeys(APPROACHES,None);max_speed=dict.fromkeys(APPROACHES,0)
        waits=dict.fromkeys(APPROACHES,0)
        for key,x,distance in projected:
            approach=key[0];prior=self.tracks.get(key)
            speed=None
            stopped_since=None
            if prior:
                dt=now-prior['at']
                speed=(prior['distance']-distance)/dt
                if abs(speed)>70 or abs(x-prior['x'])/dt>15:
                    healthy=False;speed=None
                stopped_since=prior['stopped_since']
            if prior is None:
                # Unknown new-track speed uses a conservative upper bound, not
                # an invented zero speed or a claimed measured velocity.
                speed=70.0
            elif speed is None:healthy=False
            if distance>=0:
                if speed is not None and abs(speed)<=.5:
                    counts[approach]+=1
                    stopped_since=now if stopped_since is None else stopped_since
                    waits[approach]=max(waits[approach],now-stopped_since)
                elif speed is not None and speed>.5:
                    approaching[approach]+=1;stopped_since=None
                    nearest[approach]=distance if nearest[approach] is None else min(nearest[approach],distance)
                    max_speed[approach]=max(max_speed[approach],speed)
                elif speed is not None:healthy=False # wrong-way movement unsupported
            # Measure actual crossing of a surveyed upstream count line. Initial
            # stationary queues and track creation are NOT vehicle arrivals.
            counted=prior['counted'] if prior else False
            line=self.calibrations[approach].length*.8
            if prior and not counted and prior['distance']>=line and distance<line:
                self.arrivals[approach].append(now);counted=True
            self.tracks[key]={'at':now,'x':x,'distance':distance,'stopped_since':stopped_since,'counted':counted}
        self.last_frame=now
        if len(self.tracks)>4000:
            self.tracks.clear();healthy=False
        for a in APPROACHES:
            while self.arrivals[a] and self.arrivals[a][0]<now-30:self.arrivals[a].popleft()
            if len(self.arrivals[a])>150 or counts[a]>500 or approaching[a]>500:healthy=False
            while len(self.arrivals[a])>150:self.arrivals[a].popleft()
            counts[a]=min(counts[a],500);approaching[a]=min(approaching[a],500)
        traffic={'downstream_counts':dict(downstream_counts),'downstream_capacity':dict(downstream_capacity),
                 'approaching':approaching,'arrival_rate':{a:len(self.arrivals[a])/30 for a in APPROACHES},'oldest_wait_s':{a:min(waits[a],3600) for a in APPROACHES}}
        metric={'nearest_moving_distance_m':nearest,'max_approach_speed_mps':max_speed,
                'distance_uncertainty_m':{a:self.calibrations[a].uncertainty for a in APPROACHES}}
        return {'counts':counts,'conflict_clear':conflict_clear,'healthy':healthy,'captured_at':captured_at,
                'traffic_state':traffic,'approach_state':metric}
