"""Isolated real bridge readiness + volume persistence; no account or live home.

PRUCE_TEST_IMAGE=pruce-whatsapp-check:local python3 tests/check_whatsapp_runtime.py
"""
import os
import subprocess
import uuid

IMAGE = os.environ.get('PRUCE_TEST_IMAGE', 'pruce-whatsapp-check:local')
volume = 'pruce-wa-offline-' + uuid.uuid4().hex


def run(code, persistent=False):
    args = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
            '--read-only', '--tmpfs', '/tmp', '--tmpfs', '/run', '--env', 'HERMES_HOME=/var/lib/hermes',
            '--env', 'HOME=/var/lib/hermes']
    args += ['--mount', f'type=volume,src={volume},dst=/var/lib/hermes'] if persistent else ['--tmpfs', '/var/lib/hermes']
    subprocess.run(args + ['--entrypoint', '/opt/hermes/.venv/bin/python3', IMAGE, '-c', code], check=True, timeout=30)


try:
    subprocess.run(['docker', 'volume', 'create', volume], check=True, capture_output=True)
    run('''import subprocess,pathlib,stat,pwd
subprocess.run(['/opt/hermes/.venv/bin/python3','/opt/plow/whatsapp-init.py'],check=True)
p=pathlib.Path('/var/lib/hermes/platforms/whatsapp/session')
assert stat.S_IMODE(p.stat().st_mode)==0o700
assert p.stat().st_uid==pwd.getpwnam('hermes').pw_uid
assert not (p/'creds.json').exists()
(p/'synthetic-marker').write_text('offline only')
print('Private unpaired directory: OK')''', True)
    run("import pathlib; assert pathlib.Path('/var/lib/hermes/platforms/whatsapp/session/synthetic-marker').read_text()=='offline only'; print('Volume survives replacement container: OK')", True)
    run('''import subprocess,urllib.request,json,time,tempfile
with tempfile.TemporaryDirectory() as tmp:
 p=subprocess.Popen(['node','/opt/hermes/scripts/whatsapp-bridge/bridge.js','--session',tmp,'--mode','bot'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for i in range(40):
   try:
    data=json.load(urllib.request.urlopen('http://127.0.0.1:3000/health',timeout=1)); break
   except Exception: time.sleep(.25)
  else: raise AssertionError('Bridge HTTP unavailable')
  assert p.poll() is None
  assert data.get('status')!='connected'
  print('Official bridge HTTP ready offline; unauthenticated:',data.get('status'))
 finally:
  p.terminate(); p.wait(timeout=10)
from pathlib import Path
sources = next(Path('/package/admin').glob('s6-overlay-*/etc/s6-rc/sources'))
subprocess.run(['/command/s6-rc-compile','/tmp/s6-check',str(sources),'/etc/s6-overlay/s6-rc.d'],check=True)
print('s6 dependency graph: OK')''')
    run('''import pathlib,subprocess,os
p=pathlib.Path('/run/s6/container_environment'); p.mkdir(parents=True)
(p/'PLOW_UNRELATED_TEST_MARKER').write_text('preserved')
env=dict(os.environ,WHATSAPP_ENABLED='true',WHATSAPP_ALLOWED_USERS='*')
subprocess.run(['/opt/hermes/.venv/bin/python3','/opt/plow/whatsapp-init.py'],env=env,check=True)
assert (p/'WHATSAPP_ENABLED').read_text()=='false'
assert (p/'PLOW_UNRELATED_TEST_MARKER').read_text()=='preserved'
print('Invalid WhatsApp settings disable only WhatsApp: OK')''')
finally:
    subprocess.run(['docker', 'volume', 'rm', volume], check=True, capture_output=True)
