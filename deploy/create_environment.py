"""Create a private initial environment file without displaying credentials."""
import argparse
import os
from pathlib import Path
import secrets
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('path',type=Path)
a=p.parse_args()
# Exclusive creation: rerunning must never rotate credentials silently.
fd=os.open(a.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
    f.write('SABZ_BIND=127.0.0.1\nSABZ_PORT=8099\n')
    f.write('SABZ_SOURCE_ID=junction-001-sensor\n')
    f.write('SABZ_STATE_PATH=/var/lib/sabz/edge.sqlite3\n')
    f.write('SABZ_TIMING_FILE=/etc/sabz/timing.json\n')
    f.write('SABZ_CAMERA_TOKEN='+secrets.token_urlsafe(32)+'\n')
    f.write('SABZ_READER_TOKEN='+secrets.token_urlsafe(32)+'\n')
print('Created configuration. Credentials were not printed. On Windows, restrict file ACLs separately.')
