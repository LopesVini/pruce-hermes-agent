"""Audit the shipped official Google scripts offline; no real OAuth credentials."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

SCRIPTS = Path('/opt/hermes/skills/productivity/google-workspace/scripts')


@unittest.skipUnless((SCRIPTS / 'setup.py').exists(), 'installed Hermes required')
class OfficialGoogleTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, '/opt/hermes')
        sys.path.insert(0, str(SCRIPTS))
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        self.tmp = tempfile.TemporaryDirectory(prefix='google-offline-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        self.setup = self.load('setup.py')
        self.api = self.load('google_api.py')

    def load(self, name):
        spec = importlib.util.spec_from_file_location('audit_google_' + name[:-3], SCRIPTS / name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def store_fixture_client(self):
        # Intentionally nonfunctional client. Only local authorization URL construction.
        source = self.home / 'fixture-client.json'
        source.write_text(json.dumps({'installed': {
            'client_id': 'offline-fixture.apps.googleusercontent.com',
            'client_secret': 'offline-fixture-not-a-secret',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://localhost'],
        }}))
        with contextlib.redirect_stdout(io.StringIO()):
            self.setup.store_client_secret(str(source))

    def test_exact_dependencies_already_installed(self):
        self.assertEqual(self.setup._missing_required_packages(), [])

    def test_real_headless_url_builder_persists_pkce_and_state(self):
        self.store_fixture_client()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.setup.get_auth_url()
        params = parse_qs(urlparse(output.getvalue().strip()).query)
        pending = self.setup._load_pending_auth()
        self.assertEqual(params['redirect_uri'], ['http://localhost:1'])
        self.assertEqual(params['access_type'], ['offline'])
        self.assertEqual(params['state'], [pending['state']])
        self.assertEqual(params['code_challenge_method'], ['S256'])
        self.assertGreaterEqual(len(pending['code_verifier']), 43)
        self.assertEqual(pending['redirect_uri'], 'http://localhost:1')
        self.assertFalse(self.setup.TOKEN_PATH.exists())

    def test_full_callback_state_mismatch_rejected_before_exchange(self):
        self.store_fixture_client()
        with contextlib.redirect_stdout(io.StringIO()):
            self.setup.get_auth_url()
            with self.assertRaises(SystemExit):
                self.setup.exchange_auth_code('http://localhost:1/?code=offline-fixture&state=wrong')
        self.assertFalse(self.setup.TOKEN_PATH.exists())

    def test_all_credential_paths_follow_deployment_home(self):
        for name in ('TOKEN_PATH', 'CLIENT_SECRET_PATH', 'PENDING_AUTH_PATH'):
            self.assertEqual(getattr(self.setup, name).parent, self.home)
        self.assertEqual(self.api.TOKEN_PATH, self.setup.TOKEN_PATH)
        self.store_fixture_client()
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        with tempfile.TemporaryDirectory() as other:
            token = set_hermes_home_override(other)
            try:
                independent = self.load('setup.py')
                self.assertFalse(independent.CLIENT_SECRET_PATH.exists())
                self.assertFalse(independent.TOKEN_PATH.exists())
            finally:
                reset_hermes_home_override(token)

    def test_google_reads_fail_closed_without_credentials_and_without_mac(self):
        import os
        env = dict(os.environ, HERMES_HOME=str(self.home))
        for command in (['gmail', 'search', 'is:unread', '--max', '1'], ['calendar', 'list']):
            result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'google_api.py'), *command],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Not authenticated', result.stderr)
            self.assertNotIn('Latch', result.stderr)


if __name__ == '__main__':
    unittest.main()
