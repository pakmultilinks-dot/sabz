"""Local HTTPS installation: provision/start/status. Hardware outputs emulated.
Provision requires cryptography. Runtime/status use only the standard library.
"""
import argparse
import datetime
import ipaddress
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
import urllib.request

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['provision','start','status'])
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--port',type=int,default=18099)
    a=p.parse_args()
    root=a.directory.resolve()
    config=root/'instance.json'
    if a.action=='provision':
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        if config.exists():raise SystemExit('Existing installation retained; refusing credential replacement.')
        if not root.is_dir():raise SystemExit('Create and restrict the installation directory before provisioning.')
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SABZ local development installation')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
              .not_valid_after(now+datetime.timedelta(days=30))
              .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
              .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
              .sign(key,hashes.SHA256()))
        (root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        fd=os.open(root/'key.pem',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        settings=dict(SABZ_BIND='127.0.0.1',SABZ_PORT=str(a.port),SABZ_SOURCE_ID='local-installed-sensor',
                      SABZ_CAMERA_TOKEN=secrets.token_urlsafe(32),SABZ_READER_TOKEN=secrets.token_urlsafe(32),
                      SABZ_STATE_PATH=str(root/'edge.sqlite3'),SABZ_TLS_CERT=str(root/'cert.pem'),SABZ_TLS_KEY=str(root/'key.pem'))
        fd=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(settings,f)
        print('Provisioned loopback HTTPS installation. Secrets not displayed; certificate expires in 30 days.')
    elif a.action=='start':
        settings=json.loads(config.read_text(encoding='utf-8'))
        # Avoid inheriting unrelated SABZ configuration from the launching shell.
        for k in list(os.environ):
            if k.startswith('SABZ_'):os.environ.pop(k)
        os.environ.update(settings)
        from sabz_edge.preflight import inspect
        report=inspect()
        if not report['installation_ready']:raise SystemExit(json.dumps(report))
        (root/'process.json').write_text(json.dumps({'pid':os.getpid(),'executable':sys.executable}),encoding='utf-8')
        from sabz_edge.server import main
        # Service main has its own parser; do not pass this launcher's arguments.
        sys.argv=[sys.argv[0]]
        main()
    else:
        settings=json.loads(config.read_text(encoding='utf-8'))
        context=ssl.create_default_context(cafile=settings['SABZ_TLS_CERT'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        req=urllib.request.Request('https://127.0.0.1:'+settings['SABZ_PORT']+'/v1/status',headers={'Authorization':'Bearer '+settings['SABZ_READER_TOKEN']})
        with opener.open(req,timeout=3) as response:print(json.dumps(json.load(response),indent=2))


if __name__=="__main__":main()
