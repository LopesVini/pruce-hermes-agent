import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ru_delivery_patch', ROOT / 'image/patch_ru_delivery.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)
MENU = '🍽️ RU II — almoço de 17/09/2026\nPrincipal: Synthetic dish\nSobremesa: Synthetic fruit'


def job(once=False):
    key = '012345abcdef'
    return {'id': 'synthetic-id', 'no_agent': True,
            'name': f'pruce-ru-once:{key}' if once else 'pruce-ru-daily',
            'script': f'pruce-ru-once-{key}.py' if once else 'pruce-ru-daily.py',
            'prompt': json.dumps({'kind': 'pruce_ru_once_v1' if once else 'pruce_ru_daily_v1',
                                  'opt_in': True, 'key': key})}


class PatchGuardTests(unittest.TestCase):
    def test_changed_base_source_cannot_be_patched_silently(self):
        with self.assertRaises(RuntimeError):
            patcher.patch_source(b'changed upstream source')


@unittest.skipUnless(Path('/opt/hermes/cron/scheduler_delivery.py').exists(), 'requires pinned Hermes image')
class NativeDeliveryPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, '/opt/hermes')
        from cron import scheduler_delivery
        cls.delivery = scheduler_delivery

    def deliver(self, record, live=True, wrap=True, failure=False):
        # Run the real formatter/media path; stub only routing/config and the
        # sender boundary. No gateway/channel or owner credentials are touched.
        d = self.delivery
        capture = []
        def send(target, content, *args, **kwargs):
            capture.append(content)
            return True
        with patch.object(d, '_resolve_delivery_targets', return_value=[{'platform': 'telegram', 'chat_id': 'synthetic'}]), \
             patch.object(d._sched, 'load_config', return_value={'cron': {'wrap_response': wrap}}), \
             patch('gateway.config.load_gateway_config', return_value=SimpleNamespace()), \
             patch.object(d, '_prepare_target_delivery', return_value=SimpleNamespace(live_adapter_ready=live)), \
             patch.object(d, '_deliver_via_live_adapter', side_effect=send), \
             patch.object(d, '_deliver_standalone', side_effect=send), \
             patch.object(d, '_record_delivery_verification'), \
             patch.object(d, '_cron_mirror_delivery_enabled', return_value=False):
            result = d._deliver_result(record, MENU, for_failure=failure)
        self.assertIsNone(result)
        self.assertEqual(len(capture), 1)
        return capture[0]

    def test_once_and_daily_reach_live_sender_with_exact_menu_only(self):
        for once in (False, True):
            record = job(once)
            before = json.dumps(record, sort_keys=True)
            self.assertEqual(self.deliver(record), MENU)
            self.assertEqual(json.dumps(record, sort_keys=True), before)

    def test_once_and_daily_standalone_fallback_get_exact_menu_only(self):
        for once in (False, True):
            self.assertEqual(self.deliver(job(once), live=False), MENU)

    def test_other_jobs_and_lookalikes_keep_native_presentation(self):
        for record in ({**job(), 'name': 'other'}, {**job(), 'script': 'other.py'},
                       {**job(), 'no_agent': False}, {**job(), 'prompt': '{}'},
                       {**job(), 'prompt': 'broken'}, {**job(), 'prompt': '[]'}):
            delivered = self.deliver(record)
            self.assertIn('Cronjob Response:', delivered)
            self.assertIn('(job_id: synthetic-id)', delivered)
            self.assertIn('To stop or manage this job', delivered)

    def test_native_global_opt_out_and_failure_presentation_remain_intact(self):
        self.assertEqual(self.deliver({**job(), 'name': 'other'}, wrap=False), MENU)
        self.assertIn('Cronjob Response:', self.deliver(job(), failure=True))


if __name__ == '__main__':
    unittest.main()
