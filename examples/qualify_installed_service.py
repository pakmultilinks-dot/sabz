"""Qualify the running loopback HTTPS installation using synthetic inputs."""
import argparse
import json
import math
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request
from sabz_edge.client import CameraClient, NoRedirect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('validation/installed-service-qualification.json'))
    args=parser.parse_args()
    root=args.directory.resolve()
    cfg=json.loads((root/'instance.json').read_text(encoding='utf-8'))
    assert cfg['SABZ_BIND']=='127.0.0.1','This harness only exercises loopback installations.'
    origin='https://127.0.0.1:'+cfg['SABZ_PORT']
    context=ssl.create_default_context(cafile=cfg['SABZ_TLS_CERT'])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect,urllib.request.HTTPSHandler(context=context))
    def request(path,token,body=None):
        headers={'Authorization':'Bearer '+token}
        if body is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(origin+path,body,headers)
        try:
            with opener.open(req,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:return response.code,json.load(response)
    def status():
        code,data=request('/v1/status',cfg['SABZ_READER_TOKEN'])
        assert code==200,(code,data)
        actual=data['cabinet_readback']
        assert actual and not actual['fault'] and not data['error'],data
        assert not (any(actual['lamps'][a]!='RED' for a in 'NS') and any(actual['lamps'][a]!='RED' for a in 'EW'))
        return data
    client=CameraClient(origin,cfg['SABZ_CAMERA_TOKEN'],str(root/'qualification-sender.sqlite3'),ca_file=cfg['SABZ_TLS_CERT'])
    rates=[];samples=[];checks={}
    traffic={k:dict.fromkeys('NSEW',v) for k,v in [('downstream_counts',0),('downstream_capacity',20),('approaching',0),('arrival_rate',0),('oldest_wait_s',0)]}
    approach={'nearest_moving_distance_m':dict.fromkeys('NSEW',None),'max_approach_speed_mps':dict.fromkeys('NSEW',0),'distance_uncertainty_m':dict.fromkeys('NSEW',1)}
    def send():return client.send(dict.fromkeys('NSEW',10),conflict_clear=True,traffic_state=traffic,approach_state=approach)
    try:
        for _ in range(40):
            started=time.perf_counter()
            result=send();sequence=result['accepted_sequence'];submitted=time.perf_counter()
            deadline=time.monotonic()+1
            while True:
                data=status();out=data['last_output'];actual=data['cabinet_readback']
                if out.get('observation_sequence')==sequence and actual['acknowledged_sequence']>=out['command_sequence']:break
                assert time.monotonic()<deadline,'No correlated command acknowledgement within one second'
                time.sleep(.08)
            latency=time.perf_counter()-started
            rates.append(latency*1000)
            samples.append({'software_api_to_observed_command_ack_ms':round(latency*1000,3),'stage':actual['stage'],'ready':data['ready'],
                            'submission':client.last_timings,'post_acceptance_poll_ms':round((time.perf_counter()-submitted)*1000,3)})
            time.sleep(.15)
        checks['green_observed']=any(s['stage']=='GREEN' for s in samples)
        checks['unauthorized_rejected']=request('/v1/status','invalid-credential')[0]==401
        checks['reader_cannot_publish']=request('/v1/observations',cfg['SABZ_READER_TOKEN'],b'{}')[0]==401
        checks['malformed_observation_rejected']=request('/v1/observations',cfg['SABZ_CAMERA_TOKEN'],b'{"counts":NaN}')[0]==400
        body=json.dumps({'schema_version':1,'sequence':sequence,'captured_at':time.time(),'counts':dict.fromkeys('NSEW',0),'healthy':True,'conflict_clear':True}).encode()
        checks['replay_rejected']=request('/v1/observations',cfg['SABZ_CAMERA_TOKEN'],body)[0]==409
        # Feed loss: poll without refreshing observations. Full yellow must elapse.
        deadline=time.monotonic()+7.5
        feed_loss=[]
        while time.monotonic()<deadline:
            data=status();feed_loss.append(data)
            time.sleep(.25)
        checks['feed_loss_not_ready']=not feed_loss[-1]['ready']
        checks['feed_loss_all_red']=feed_loss[-1]['cabinet_readback']['stage']=='ALL_RED'
        checks['feed_loss_yellow_observed']=any(s['cabinet_readback']['stage']=='YELLOW' for s in feed_loss)
        recovered=False
        for _ in range(20):
            send();data=status()
            recovered |= data['ready'] and data['cabinet_readback']['stage']=='GREEN'
            time.sleep(.2)
        checks['feed_recovery']=recovered
        rates.sort()
        percentile=lambda p:round(rates[max(0,math.ceil(len(rates)*p)-1)],3)
        report={'passed':all(checks.values()),'endpoint':origin,'tls_verified':True,'physical_hardware':False,'synthetic_input':True,
                'checks':checks,'samples':samples,'software_latency_ms':{'p50':percentile(.5),'p95':percentile(.95),'p99':percentile(.99),'max':round(max(rates),3),'over_200_ms':sum(v>200 for v in rates)},
                'measurement_scope':'Client POST start to polled acknowledgement of the corresponding controller command, including TLS/SQLite/control scheduling/polling. Excludes camera capture, physical lamps and external network. A command acknowledgement is not proof of a lamp transition.'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
        assert report['passed'],'Qualification failed; inspect report.'
    finally:client.close()

if __name__=='__main__':main()
