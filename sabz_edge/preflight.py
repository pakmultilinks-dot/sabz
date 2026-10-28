"""Installation checks. Never operates lamps or alters the replay database."""
from contextlib import closing
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import ssl
import tempfile
from .server import Settings


def inspect(env=None):
    checks=[]
    def add(name,ok,detail):checks.append({'name':name,'ok':bool(ok),'detail':detail})
    try:
        settings=Settings(env)
    except Exception:
        add('configuration',False,'Invalid credentials, bind address, timing file or TLS configuration; check the installation guide. Values are deliberately omitted.')
        return {'installation_ready':False,'field_ready':False,'checks':checks}
    add('configuration',True,'Settings validated; credentials omitted.')
    if settings.cert:
        try:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(settings.cert,settings.key)
            add('tls_material',True,'Certificate/key can be loaded. Client trust, hostname and expiry still require a verified connection test.')
        except Exception:add('tls_material',False,'Certificate/key cannot be loaded.')
    else:add('tls_material',True,'Loopback-only HTTP; provide trusted TLS before connecting another device.')
    parent=Path(settings.state_path).resolve().parent
    if not parent.is_dir():
        add('state_directory',False,'Create the configured state directory and grant the service account access.')
    else:
        temporary=None
        try:
            available=shutil.disk_usage(parent).free
            add('free_disk',available>=256*1024**2,'At least 256 MiB free required for installation; ongoing retention and monitoring remain necessary.')
            fd,temporary=tempfile.mkstemp(prefix='sabz-preflight-',suffix='.sqlite3',dir=parent)
            os.close(fd)
            with closing(sqlite3.connect(temporary)) as db:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('CREATE TABLE probe(value INTEGER)')
                db.execute('INSERT INTO probe VALUES (1)')
                db.commit()
            add('durable_storage_probe',True,'Temporary SQLite write/commit succeeded; operational replay database untouched.')
        except Exception:add('durable_storage_probe',False,'Service account could not create and commit a temporary SQLite database.')
        finally:
            if temporary:
                for suffix in ('','-journal','-wal','-shm'):
                    Path(temporary+suffix).unlink(missing_ok=True)
    return {'installation_ready':all(c['ok'] for c in checks),'field_ready':False,
            'output_adapter':'independent-process emulator', 'checks':checks,
            'field_blockers':['No physical cabinet adapter or electrical readback.',
                              'No calibrated 70-metre sensor or independently validated conflict-zone sensor.',
                              'No approved site movement plan, timings or physical conflict monitor.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-field-ready',action='store_true')
    args=parser.parse_args()
    report=inspect()
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['installation_ready'] and not args.require_field_ready else 1)

if __name__=='__main__':main()
