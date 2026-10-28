# Install and operate SABZ

Current scope: installable edge software with EMULATED outputs. This guide does
not connect road lamps. Physical cabinet integration and calibrated sensing
remain development work. No surveillance feed permissions are assumed.

## 1. Run the software on the existing Windows computer

From the repository root in PowerShell, with Python 3.11 or newer:

```powershell
python -m venv .venv-install
.\.venv-install\Scripts\python.exe -m pip install .
New-Item -ItemType Directory -Force data | Out-Null
$env:SABZ_CAMERA_TOKEN = .\.venv-install\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SABZ_READER_TOKEN = .\.venv-install\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SABZ_STATE_PATH = Join-Path $PWD 'data/edge.sqlite3'
$env:SABZ_TIMING_FILE = Join-Path $PWD 'config/bench-timing.json'
.\.venv-install\Scripts\python.exe -m sabz_edge.preflight
.\.venv-install\Scripts\python.exe -m sabz_edge.server
```

Keep this terminal open. The credentials are process environment variables;
copy them only through an approved local secret mechanism to the sensor and
monitor processes. Do not publish them or place them in command-line URLs.
Closing this shell loses its generated credentials. Provision persistent secrets
for a managed installation rather than generating new ones each startup.

No sensor is attached by these commands. All-red while waiting for data is the
expected startup state. Do not use a fabricated clearance value as real sensing.
Use Ctrl+C for orderly shutdown. Retain the database across restarts; it contains
anti-replay watermarks. Never delete it just to accept an old sensor packet.

## 2. Managed Linux installation on an edge computer

This systemd configuration is supplied for review; Linux service startup has
not been executed on this Windows development machine. Commands below assume
Python 3.11+, venv support and systemd are already installed, and the repository
is checked out at `/opt/sabz`. Run administrative commands as an administrator.

```sh
sudo useradd --system --home-dir /var/lib/sabz --shell /usr/sbin/nologin sabz
sudo install -d -m 0750 -o root -g sabz /etc/sabz
sudo install -d -m 0700 -o sabz -g sabz /var/lib/sabz
sudo python3 -m venv /opt/sabz/venv
sudo /opt/sabz/venv/bin/python -m pip install /opt/sabz
sudo /opt/sabz/venv/bin/python /opt/sabz/deploy/create_environment.py /etc/sabz/edge.env
sudo install -m 0640 -o root -g sabz /opt/sabz/config/bench-timing.json /etc/sabz/timing.json
sudo install -m 0644 /opt/sabz/deploy/systemd/sabz-edge.service /etc/systemd/system/sabz-edge.service
sudo systemd-analyze verify /etc/systemd/system/sabz-edge.service
sudo systemctl daemon-reload
sudo systemctl enable --now sabz-edge
sudo systemctl status sabz-edge
sudo journalctl -u sabz-edge --since '10 minutes ago'
```

Skip `useradd` if the service account already exists. The environment generator
refuses to overwrite an existing file; it never silently rotates credentials.
The environment file is root-only (0600); systemd reads it before changing to
the service account. Keep the installed software root-owned and not writable by
`sabz`. The service writes only its state directory and private temporary files.
It runs a preflight check before startup and limits repeated crash restarts.
A passing preflight checks installation prerequisites, not safe field operation.

## 3. Connect another device securely

The default listener is loopback. To use a separate sensor host, configure the
edge's PRIVATE numeric interface address in `SABZ_BIND`, then set
`SABZ_TLS_CERT` and `SABZ_TLS_KEY` in `/etc/sabz/edge.env`. Use a certificate
issued by your organization/private CA, with the actual host/IP in its SAN.
The key must be readable by the service account and protected from other users.
Restrict port 8099 to authorized sensor/monitor addresses on the private network.
Restart the service after configuration changes. Never disable TLS verification.

Use `CameraClient` with a private-CA `ca_file` when needed. Its SQLite sequence
state must persist on the sensor device. Send counts and schema-3 calibrated
metric aggregates, not camera images. The same physical observation must also
establish `healthy` and independently validated `conflict_clear`. An empty queue
is not evidence of a clear intersection. The legacy `sabz_live.py` does not
provide this calibration or clearance and cannot release green by itself.

## 4. Check operation and maintain it

From an authorized monitoring process with the reader token in its environment:

```powershell
Invoke-RestMethod http://127.0.0.1:8099/v1/status -Headers @{Authorization="Bearer $env:SABZ_READER_TOKEN"}
Invoke-RestMethod http://127.0.0.1:8099/readyz -Headers @{Authorization="Bearer $env:SABZ_READER_TOKEN"}
```

For remote monitoring replace the origin with the verified HTTPS origin.
Check sensor age, faults and `cabinet_readback` separately from requested lamps.
`ready` means the software loop has usable data; `field_ready` remains false.
Monitor disk usage: the audit database currently has no automatic retention.
Use SQLite backup facilities for a live backup. Retention must preserve replay
watermarks. Keep secrets out of support bundles. Test backups/restoration offline.

On Linux, use `sudo systemctl stop sabz-edge` for maintenance and `start` to
resume. A latched fault needs investigation before restart. Software shutdown
only controls the emulator; actual power-loss behaviour requires physical
cabinet engineering. For upgrades, stop, back up, install a tested package,
preflight and start. Do not mix old code with an unreviewed changed database.

## 5. What must be built before physical installation

1. A locally authorized, calibrated sensor pipeline: metric distances/speeds,
   motorcycles, occlusion, health and conflict-zone sensing, with measured latency.
2. A physical controller adapter for a selected documented interface. It needs
   ordered commands, independent local timing, actual readback and disconnect
   handling. The current process pipe is not that interface.
3. An independent physical conflict monitor/watchdog, manual override and
   site-engineered power-loss behaviour. A second process on the same PC does
   not provide this boundary.
4. A movement plan including turns, pedestrians and emergency handling, approved
   timings, and controlled hardware-in-loop acceptance on the chosen equipment.

No change to an environment flag can supply these missing components. The
installation above is useful for integrating and testing real local sensors,
while keeping signal outputs emulated. Do not wire its outputs to road relays.

## Verified local HTTPS installation (27 October 2026)

A background instance is running on this development computer at
`https://127.0.0.1:18099`. It uses the installed `.venv-edge-test` package and
independent-process cabinet emulator. It is private to this computer, not an
Internet deployment. No camera or physical output is connected. After tests,
the synthetic sender stopped and the service returned to all-red/not-ready.

Check it from the repository root without displaying credentials:

```powershell
python deploy/local_instance.py status --directory data/local-installation
```

The utility verifies TLS using the installation's private local trust material;
it does not disable verification or add a system-wide trusted CA. Its development
certificate expires 30 days after provisioning. Credentials, keys and persistent
replay state live in the gitignored `data/local-installation` directory. That
directory's Windows ACL was restricted to the current user and SYSTEM. Keep it
private; do not send it with support reports. Its running process is a background
process, not a registered Windows auto-start service.

The following command actively injects SYNTHETIC traffic and clearance assertions
into this emulator and tests feed loss/recovery. It is not a real sensor adapter:

```powershell
python -m examples.qualify_installed_service --directory data/local-installation
```

The service records the observation sequence associated with each requested
command, allowing a client to correlate input acceptance and emulated command
acknowledgement. An acknowledgement still does not imply a lamp transition.
The host loop targets 20 Hz with start-to-start pacing. This is soft real time,
not a guaranteed deadline on Windows or Linux.

To stop this owned installation, first check its status and confirm no hardware
has been connected. Read `data/local-installation/process.json`, inspect the
corresponding process command line, and terminate only the matching
`local_instance.py start --directory ...local-installation` process. Its emulator
has independent lease expiry. Do not terminate arbitrary Python processes.
To restart in a foreground terminal (Ctrl+C stops it):

```powershell
.\.venv-edge-test\Scripts\python.exe -B deploy/local_instance.py start --directory data/local-installation
```

Do not run another copy while it is active; the persistent-state lock rejects
concurrent ownership. Do not rerun provisioning to rotate credentials; it refuses
to overwrite an existing installation. The current launcher's environment is
isolated from unrelated `SABZ_*` shell settings.

Evidence is in `validation/deployment-report.json`,
`validation/installed-service-after-scheduling.json`,
`validation/deployment-soak-final.json`, and
`validation/deployment-virtual-qualification.json`. The 40-sample software latency
measurement includes TLS, durable acceptance, host scheduling and status polling;
it excludes camera capture, external networks and physical lamps. Its observed
maximum is not a guaranteed bound. Docker's Linux engine was unavailable; no
container or systemd runtime success is claimed.
