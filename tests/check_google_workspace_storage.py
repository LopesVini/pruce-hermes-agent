"""Official OAuth pending/client storage across replacement containers, offline.

No token exchange or real credentials. Uses a disposable isolated Docker volume.
"""
import os
import subprocess
import uuid

IMAGE = os.environ.get('PRUCE_TEST_IMAGE', 'pruce-whatsapp-check:local')
volume = 'pruce-google-offline-' + uuid.uuid4().hex


def run(code):
    subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
                    '--read-only', '--tmpfs', '/tmp', '--env', 'HERMES_HOME=/audit-home',
                    '--mount', f'type=volume,src={volume},dst=/audit-home',
                    '--entrypoint', '/opt/hermes/.venv/bin/python3', IMAGE, '-B', '-c', code],
                   check=True, timeout=30)


try:
    subprocess.run(['docker', 'volume', 'create', volume], check=True, capture_output=True)
    run('''import sys,importlib.util,os,json,pathlib,contextlib,io
os.umask(0o077)
directory='/opt/hermes/skills/productivity/google-workspace/scripts'
sys.path.insert(0,directory)
s=importlib.util.spec_from_file_location('audit_setup',directory+'/setup.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
source=pathlib.Path('/tmp/fixture-client.json')
source.write_text(json.dumps({'installed':{'client_id':'offline-fixture.apps.googleusercontent.com','client_secret':'offline-fixture-not-secret','auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token'}}))
with contextlib.redirect_stdout(io.StringIO()):
 m.store_client_secret(str(source)); m.get_auth_url()
assert m.CLIENT_SECRET_PATH.parent==pathlib.Path('/audit-home')
assert m.PENDING_AUTH_PATH.exists()
assert not m.TOKEN_PATH.exists()
print('Official headless URL + private pending/client storage: OK (fixture only)')''')
    run('''import sys,importlib.util,pathlib,stat
directory='/opt/hermes/skills/productivity/google-workspace/scripts';sys.path.insert(0,directory)
s=importlib.util.spec_from_file_location('audit_setup',directory+'/setup.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert m._load_pending_auth()['code_verifier']
for p in (m.PENDING_AUTH_PATH,m.CLIENT_SECRET_PATH):
 assert stat.S_IMODE(p.stat().st_mode)==0o600
assert not m.TOKEN_PATH.exists()
print('Pending OAuth/client fixture survives replacement container: OK; no authenticated token')''')
finally:
    subprocess.run(['docker', 'volume', 'rm', volume], check=True, capture_output=True)
