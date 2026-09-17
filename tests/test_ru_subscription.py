from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/pruce-ru/scripts'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sub = load('ru_subscription_test', SCRIPTS / 'subscription.py')
daily = load('ru_daily_test', SCRIPTS / 'daily.py')
NOW = datetime.fromisoformat('2026-09-17T12:00:00+00:00')


class SubscriptionLogicTests(unittest.TestCase):
    def test_11h_brasilia_translates_to_14h_utc(self):
        self.assertEqual(sub.schedule_expression('11:00', 'daily', 'America/Sao_Paulo',
                                                ZoneInfo('UTC'), NOW), '0 14 * * *')

    def test_weekday_shift_and_same_zone(self):
        self.assertEqual(sub.schedule_expression('23:00', 'weekdays', 'America/Sao_Paulo',
                                                ZoneInfo('UTC'), NOW), '0 2 * * 2,3,4,5,6')
        self.assertEqual(sub.schedule_expression('11:00', 'weekdays', 'America/Sao_Paulo',
                                                ZoneInfo('America/Sao_Paulo'), NOW), '0 11 * * 1,2,3,4,5')

    def test_dst_mismatch_and_ambiguous_time_refuse_schedule(self):
        for at, zone in (('antes do almoço', 'America/Sao_Paulo'),
                         ('11:00', 'America/New_York'), ('25:00', 'America/Sao_Paulo')):
            with self.assertRaises(ValueError):
                sub.schedule_expression(at, 'daily', zone, ZoneInfo('UTC'), NOW)

    def test_no_explicit_opt_in_touches_no_runtime_or_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sub, 'native_runtime') as native:
            with self.assertRaises(ValueError):
                sub.manage({'action': 'subscribe'}, home=Path(directory))
            native.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_daily_only_published_nonempty_menu_and_fresh_query(self):
        job = {'name': sub.NAME, 'script': sub.SCRIPT, 'enabled': True,
               'prompt': json.dumps({'kind': sub.MARKER, 'ru': 'setorial_2', 'opt_in': True})}
        query = Mock(return_value={'status': 'ok', 'items': [{'descricao': 'Synthetic dish'}],
                                  'text': '🍽️ Synthetic menu'})
        self.assertEqual(daily.render([job], query), '🍽️ Synthetic menu')
        query.assert_called_once_with(ru='setorial_2', when='hoje', meal='almoço')
        for status in ('not_published', 'source_unavailable', 'invalid_request'):
            query.return_value = {'status': status, 'text': 'failure'}
            self.assertEqual(daily.render([job], query), '')
        query.return_value = {'status': 'ok', 'items': [], 'text': 'no item'}
        self.assertEqual(daily.render([job], query), '')
        self.assertEqual(daily.render([], query), '')
        self.assertEqual(daily.render([job, job], query), '')
        self.assertEqual(daily.render([{**job, 'enabled': False}], query), '')

    def test_daily_failure_has_empty_stdout_and_zero_exit(self):
        with patch.object(daily, 'render', side_effect=OSError('source error')), patch('sys.stdout') as out:
            daily.main()
        out.write.assert_not_called()


@unittest.skipUnless(Path('/opt/hermes/cron/jobs.py').exists(), 'requires native Hermes scheduler')
class NativeSubscriptionTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, '/opt/hermes')
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        self.jobs, self.scheduler, self.clock = sub.native_runtime()
        self.enterContext(self.jobs.use_cron_store(self.home))
        self.enterContext(patch.dict('os.environ', {'HERMES_HOME': str(self.home), 'HERMES_TIMEZONE': 'UTC'}))
        self.enterContext(patch.object(self.clock, 'now', return_value=NOW))
        self.enterContext(patch.object(self.jobs, '_hermes_now', return_value=NOW))
        sub.state.run(self.home / 'pruce/state.json', 'profile', {'profile': {
            'timezone': {'status': 'known', 'value': 'America/Sao_Paulo', 'city': 'Belo Horizonte'}}})

    def manage(self, **kwargs):
        return sub.manage(kwargs, self.home, (self.jobs, self.scheduler, self.clock))

    def subscribe(self, **kwargs):
        return self.manage(**{'action': 'subscribe', 'opt_in': True, 'ru': 'RU II',
                             'time': '11:00', 'days': 'daily', 'deliver': 'imessage:synthetic-owner', **kwargs})

    def test_ru_ii_daily_11_native_store_provider_and_persistent_preference(self):
        result = self.subscribe()
        job = self.jobs.get_job(result['job_id'])
        self.assertEqual(job['schedule']['expr'], '0 14 * * *')
        self.assertEqual(job['next_run_at'], '2026-09-17T14:00:00+00:00')
        self.assertTrue(job['no_agent'])
        self.assertEqual(job['failure_deliver'], 'local')
        self.assertEqual(job['deliver'], 'imessage:synthetic-owner')
        self.assertEqual(sub.configuration(job)['timezone'], 'America/Sao_Paulo')
        self.assertTrue((self.home / 'cron/jobs.json').exists())
        self.assertTrue((self.home / 'scripts' / sub.SCRIPT).exists())
        saved = sub.state.run(self.home / 'pruce/state.json', 'read')
        self.assertEqual(saved['profile']['preferred_ru'], 'setorial_2')
        self.assertEqual(saved['tasks'], [])

    def test_ru_i_weekdays(self):
        result = self.subscribe(ru='RU I', days='weekdays')
        self.assertEqual(self.jobs.get_job(result['job_id'])['schedule']['expr'], '0 14 * * 1,2,3,4,5')

    def test_idempotent_request_and_change_ru_keeps_one_job_and_delivery(self):
        first = self.subscribe()
        second = self.subscribe()
        changed = self.manage(action='subscribe', opt_in=True, ru='RU I')
        self.assertEqual(first['job_id'], second['job_id'])
        self.assertEqual(first['job_id'], changed['job_id'])
        self.assertEqual(len(self.jobs.load_jobs()), 1)
        job = self.jobs.load_jobs()[0]
        self.assertEqual(sub.configuration(job)['ru'], 'setorial_1')
        self.assertEqual(job['deliver'], 'imessage:synthetic-owner')
        self.assertEqual(job['repeat']['times'], None)

    def test_cancel_preserves_other_jobs_state_and_preference(self):
        self.subscribe()
        other = self.jobs.create_job('Synthetic unrelated', '0 8 * * *', name='other', deliver='local')
        before = (self.home / 'pruce/state.json').read_bytes()
        self.assertEqual(self.manage(action='cancel')['status'], 'cancelled')
        self.assertEqual([job['id'] for job in self.jobs.load_jobs()], [other['id']])
        self.assertEqual((self.home / 'pruce/state.json').read_bytes(), before)
        self.assertEqual(self.manage(action='status')['status'], 'inactive')
        self.assertEqual(self.manage(action='cancel')['status'], 'cancelled')

    def test_unknown_ru_time_timezone_or_target_does_not_create_job(self):
        for data in ({'ru': 'unknown'}, {'time': 'antes do almoço'}, {'days': None},
                     {'timezone': 'Invalid/Zone'}, {'deliver': 'all'}, {'deliver': 'origin'},
                     {'deliver': 'local'}, {'deliver': 'imessage:a,imessage:b'}):
            with self.assertRaises((ValueError, KeyError)):
                self.subscribe(**data)
            self.assertEqual(self.jobs.load_jobs(), [])
        sub.state.run(self.home / 'pruce/state.json', 'profile', {'profile': {
            'timezone': {'status': 'pending', 'value': None, 'city': None}}})
        with self.assertRaises(ValueError):
            self.subscribe()
        self.assertEqual(self.jobs.load_jobs(), [])

    def test_consolidates_only_our_duplicate_jobs(self):
        first = self.subscribe()
        original = self.jobs.get_job(first['job_id'])
        self.jobs.create_job(original['prompt'], '0 14 * * *', name=sub.NAME,
                             script=sub.SCRIPT, no_agent=True, deliver=original['deliver'])
        unrelated = self.jobs.create_job('Not ours', '0 8 * * *', name=sub.NAME, deliver='local')
        self.subscribe()
        self.assertEqual({job['id'] for job in self.jobs.load_jobs()}, {first['job_id'], unrelated['id']})

    def test_native_no_agent_gate_delivers_exact_menu_and_silences_failures(self):
        result = self.subscribe()
        job = self.jobs.get_job(result['job_id'])
        for output in ('🍽️ Synthetic RU menu', ''):
            with patch.object(self.scheduler, '_run_job_script_with_claim_heartbeat', return_value=(True, output)):
                ok, document, delivered, error = self.scheduler._run_no_agent_job(job, job['id'], sub.NAME, None)
            self.assertTrue(ok)
            self.assertIsNone(error)
            self.assertEqual(delivered, output or self.scheduler.SILENT_MARKER)

    def test_real_installed_wrapper_runs_silently_after_cancel(self):
        import subprocess
        self.subscribe()
        shutil.copytree(ROOT / 'skills/pruce-ru', self.home / 'skills/pruce-ru')
        shutil.copytree(ROOT / 'skills/pruce-tasks', self.home / 'skills/pruce-tasks')
        self.manage(action='cancel')
        result = subprocess.run([sys.executable, '-B', str(self.home / 'scripts' / sub.SCRIPT)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')

    def test_current_dm_captured_from_real_hermes_terminal_bridge(self):
        import os
        import subprocess
        from gateway.session_context import set_session_vars, clear_session_vars
        from tools.environments.local import _inject_session_context_env
        tokens = set_session_vars(platform='imessage', chat_id='synthetic-current-owner', chat_type='dm')
        try:
            env = dict(os.environ)
            _inject_session_context_env(env)
        finally:
            clear_session_vars(tokens)
        data = {'action': 'subscribe', 'opt_in': True, 'ru': 'RU II', 'time': '11:00', 'days': 'daily'}
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'subscription.py')],
                                input=json.dumps(data), env=env, capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout)['status'], 'scheduled', result.stdout)
        job = self.jobs.load_jobs()[0]
        self.assertEqual(job['deliver'], 'imessage:synthetic-current-owner')
        self.assertEqual(job['origin']['chat_id'], 'synthetic-current-owner')

    def test_paused_subscription_resumed_without_duplicate(self):
        result = self.subscribe()
        self.jobs.pause_job(result['job_id'])
        updated = self.subscribe()
        self.assertEqual(updated['job_id'], result['job_id'])
        self.assertTrue(self.jobs.get_job(result['job_id'])['enabled'])

    def test_cloud_registration_failure_does_not_duplicate_on_retry(self):
        from cron.scheduler import CronSchedulerRegistrationError
        provider = Mock()
        provider.register_job.side_effect = OSError('synthetic provider down')
        with patch('cron.scheduler_provider.resolve_cron_scheduler', return_value=provider):
            with self.assertRaises(CronSchedulerRegistrationError):
                self.subscribe()
        partial_id = self.jobs.load_jobs()[0]['id']
        result = self.subscribe()
        self.assertEqual(result['job_id'], partial_id)
        self.assertEqual(len(self.jobs.load_jobs()), 1)

    def test_concurrent_subprocess_requests_keep_one_native_job(self):
        import subprocess
        data = json.dumps({'action': 'subscribe', 'opt_in': True, 'ru': 'RU II',
                           'time': '11:00', 'days': 'daily', 'deliver': 'imessage:synthetic-owner'})
        processes = [subprocess.Popen([sys.executable, '-B', str(SCRIPTS / 'subscription.py')],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     text=True) for _ in range(2)]
        for process in processes:
            process.stdin.write(data)
            process.stdin.close()
            process.stdin = None
        for process in processes:
            out, err = process.communicate(timeout=25)
            self.assertEqual(json.loads(out)['status'], 'scheduled', out + err)
        self.assertEqual(len(self.jobs.load_jobs()), 1)


if __name__ == '__main__':
    unittest.main()
