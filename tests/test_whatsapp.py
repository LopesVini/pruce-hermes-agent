"""Offline contracts against the installed official Hermes, not a fake E2E."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wa_init", ROOT / "image/whatsapp_init.py")
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)


class SafetyTests(unittest.TestCase):
    def test_configuration_closed_and_single_sender(self):
        init.validate({})
        init.validate({"WHATSAPP_ENABLED": "true", "WHATSAPP_ALLOWED_USERS": "5511999999999",
                       "WHATSAPP_HOME_CHANNEL": "5511999999999@s.whatsapp.net"})
        for values in ({"WHATSAPP_ENABLED": "true"}, {"WHATSAPP_ALLOWED_USERS": "*"},
                       {"WHATSAPP_ALLOWED_USERS": "5511999999999,5511888888888"},
                       {"WHATSAPP_ALLOW_ALL_USERS": "true"}, {"WHATSAPP_GROUP_POLICY": "open"},
                       {"WHATSAPP_HOME_CHANNEL": "group@g.us"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                init.validate(values)


@unittest.skipUnless(Path('/opt/hermes/plugins/platforms/whatsapp/adapter.py').exists(), 'installed Hermes required')
class NativeTests(unittest.TestCase):
    def test_deps_ready_without_runtime_install_and_unpaired_preflight(self):
        from plugins.platforms.whatsapp.adapter import WhatsAppAdapter, check_whatsapp_requirements
        from gateway.config import PlatformConfig
        self.assertTrue(check_whatsapp_requirements())
        with tempfile.TemporaryDirectory() as home:
            adapter = WhatsAppAdapter(PlatformConfig(extra={"session_path": home}))
            self.assertTrue(adapter._ensure_bridge_deps(Path(adapter._bridge_script).parent))
            self.assertFalse(adapter._preflight())  # real account still required

    def test_official_allowlist_denies_unknown_and_empty(self):
        directory = '/opt/hermes/scripts/whatsapp-bridge'
        subprocess.run(['node', '--test', 'allowlist.test.mjs', 'owner_message_gate.test.mjs'],
                       cwd=directory, check=True, capture_output=True, timeout=30)

    def test_session_keys_isolate_dms_and_channels(self):
        from gateway.session import SessionSource, build_session_key
        from gateway.config import Platform
        a = SessionSource(platform=Platform.WHATSAPP, chat_type='dm', chat_id='5511999999999@s.whatsapp.net')
        b = SessionSource(platform=Platform.WHATSAPP, chat_type='dm', chat_id='5511888888888@s.whatsapp.net')
        other = SessionSource(platform=Platform.API_SERVER, chat_type='dm', chat_id=a.chat_id)
        self.assertNotEqual(build_session_key(a), build_session_key(b))
        self.assertNotEqual(build_session_key(a), build_session_key(other))

    def test_whatsapp_flag_does_not_disable_other_platform(self):
        from gateway.config import GatewayConfig, Platform, PlatformConfig
        from gateway.config_env import _whatsapp
        config = GatewayConfig(platforms={Platform.API_SERVER: PlatformConfig(enabled=True)})
        with patch.dict(os.environ, {'WHATSAPP_ENABLED': 'true'}):
            _whatsapp(config)
        self.assertTrue(config.platforms[Platform.WHATSAPP].enabled)
        with patch.dict(os.environ, {'WHATSAPP_ENABLED': 'false'}):
            _whatsapp(config)
        self.assertFalse(config.platforms[Platform.WHATSAPP].enabled)
        self.assertTrue(config.platforms[Platform.API_SERVER].enabled)

    def test_cron_resolves_actual_origin_and_explicit_whatsapp(self):
        from cron.scheduler_delivery import _resolve_delivery_targets
        origin = {'platform': 'whatsapp', 'chat_id': '5511999999999@s.whatsapp.net'}
        for deliver in ('origin', 'whatsapp:' + origin['chat_id']):
            target = _resolve_delivery_targets({'deliver': deliver, 'origin': origin})[0]
            self.assertEqual((target['platform'], target['chat_id']), ('whatsapp', origin['chat_id']))


if __name__ == '__main__':
    unittest.main()
