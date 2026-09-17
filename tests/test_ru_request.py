from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/pruce-ru/scripts'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entry = load('ru_request_test', SCRIPTS / 'request.py')
prior = load('ru_request_native_setup', ROOT / 'tests/test_ru_subscription.py')
daily = load('ru_request_daily_test', SCRIPTS / 'daily.py')


def fixture(identifier, day):
    return {'id': identifier, 'cardapios': [{'data': day.isoformat(), 'refeicoes': [
        {'tipoRefeicao': 'Almoço', 'pratos': [
            {'tipoPrato': 'Prato protéico 1', 'descricaoPrato': 'Synthetic principal'}]}]}]}


class RequestIntentTests(unittest.TestCase):
    def test_distinct_intents_including_exact_real_failure(self):
        for text, expected in (
            ('O que tem no RU II hoje?', 'query'),
            ('O que vai ter amanhã no RU Saúde?', 'query'),
            ('Me manda o cardápio do RU II hoje às 10h54.', 'once'),
            ('Me manda o RU II às 11h.', 'once'),
            ('Me manda daqui a uma hora.', 'once'),
            ('Me manda o RU II daqui a 5 minutos.', 'once'),
            ('Me manda o RU II todo dia às 11h.', 'recurring'),
            ('Me avisa o RU I de segunda a sexta.', 'recurring'),
            ('Para de me mandar o bandejão', 'cancel'),
            ('Não quero mais o cardápio diário', 'cancel'),
            ('Troca para o RU I', 'change')):
            with self.subTest(text=text):
                self.assertEqual(entry.intent(text), expected)

    def test_future_intent_never_calls_the_immediate_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(entry.sub, 'manage', return_value={'status': 'scheduled', 'text': 'Confirmation'}) as manager:
                with patch.object(entry.sub.menu, 'query', side_effect=AssertionError('no immediate fetch')):
                    result = entry.handle({'text': 'Me manda o cardápio do RU II hoje às 10h54.'}, Path(directory))
            self.assertEqual(result['text'], 'Confirmation')
            self.assertNotIn('items', result)
            self.assertEqual(manager.call_args.args[0]['action'], 'send_once')
            self.assertEqual(manager.call_args.args[0]['time'], '10:54')

    def test_state_schema_is_optional_and_rejects_invalid_lunch_times(self):
        entry.sub.state.validate_profile(entry.sub.state.default_profile())
        value = entry.flow_value({}, pending_lunch_time='25:00')
        with self.assertRaises(ValueError):
            entry.sub.state.validate_ru_delivery(value)

    def test_effective_runtime_route_requires_entry_before_fetch(self):
        persona = (ROOT / 'runtime/persona.md').read_text()
        skill = (ROOT / 'skills/pruce-ru/SKILL.md').read_text()
        self.assertIn("request.py", persona)
        self.assertIn('before any source fetch', persona)
        self.assertIn('Never call menu.py directly for a', skill)
        self.assertIn('actual current owner', skill)


@unittest.skipUnless(Path('/opt/hermes/cron/jobs.py').exists(), 'requires native Hermes scheduler')
class NativeRequestTests(unittest.TestCase):
    setUp = prior.NativeSubscriptionTests.setUp

    def request(self, text, **extra):
        return entry.handle({'text': text, 'deliver': 'imessage:synthetic-owner', **extra},
                            self.home, (self.jobs, self.scheduler, self.clock), fetch=fixture)

    def test_immediate_query_and_first_lunch_question_without_job(self):
        result = self.request('O que tem no RU II hoje?')
        self.assertEqual(result['intent'], 'query')
        self.assertIn('Synthetic principal', result['text'])
        self.assertIn('Você costuma almoçar que horas?', result['text'])
        self.assertEqual(self.jobs.load_jobs(), [])

    def test_exact_failure_schedules_one_future_job_without_menu(self):
        with patch.object(entry.sub.menu, 'query', side_effect=AssertionError('no menu now')):
            result = self.request('Me manda o cardápio do RU II hoje às 10h54.')
        self.assertEqual(result['status'], 'scheduled')
        self.assertEqual(result['intent'], 'once')
        self.assertNotIn('items', result)
        job = self.jobs.get_job(result['job_id'])
        self.assertEqual(job['schedule']['kind'], 'once')
        self.assertEqual(job['repeat']['times'], 1)
        self.assertEqual(datetime.fromisoformat(job['schedule']['run_at']),
                         datetime.fromisoformat('2026-09-17T10:54:00-03:00'))

    def test_relative_five_minutes_and_same_timestamp_not_duplicated(self):
        first = self.request('Me manda o RU II daqui a 5 minutos.')
        second = self.request('Me manda o RU II daqui a 5 minutos.')
        self.assertEqual(first['job_id'], second['job_id'])
        self.assertEqual(len(self.jobs.load_jobs()), 1)
        self.assertEqual(datetime.fromisoformat(first['schedule']), prior.NOW + timedelta(minutes=5))

    def test_past_time_does_not_fetch_or_create(self):
        with patch.object(entry.sub.menu, 'query', side_effect=AssertionError('no fetch')):
            with self.assertRaises(entry.sub.RequestError):
                self.request('Me manda o RU II hoje às 08h.')
        self.assertEqual(self.jobs.load_jobs(), [])

    def test_recurring_route_and_changes_keep_same_job(self):
        first = self.request('Me manda o RU II todo dia às 11h.')
        changed_time = self.request('Muda o horário para às 10h.')
        changed_ru = self.request('Troca para o RU I.')
        self.assertEqual(first['job_id'], changed_time['job_id'])
        self.assertEqual(first['job_id'], changed_ru['job_id'])
        self.assertEqual(len(self.jobs.load_jobs()), 1)
        config = entry.sub.configuration(self.jobs.get_job(first['job_id']))
        self.assertEqual(config['ru'], 'setorial_1')
        self.assertEqual(config['time'], '10:00')

    def start_offer(self):
        self.request('O que tem no RU II hoje?')
        offer = self.request('Às 12h.')
        self.assertEqual(offer['status'], 'awaiting_consent')
        self.assertIn('de segunda a sexta, às 11:00', offer['text'])
        self.assertEqual(self.jobs.load_jobs(), [])
        saved = entry.sub.state.run(self.home / 'pruce/state.json', 'read')['profile']
        self.assertIsNone(saved['ru_delivery']['usual_lunch_time'])

    def test_accept_saves_usual_lunch_time_and_schedules_weekdays_only(self):
        self.start_offer()
        result = self.request('Sim.')
        self.assertEqual(result['intent'], 'accept')
        job = self.jobs.get_job(result['job_id'])
        self.assertEqual(entry.sub.configuration(job)['days'], 'weekdays')
        profile = entry.sub.state.run(self.home / 'pruce/state.json', 'read')['profile']
        self.assertEqual(profile['preferred_ru'], 'setorial_2')
        self.assertEqual(profile['ru_delivery']['usual_lunch_time'], '12:00')
        self.assertEqual(len(self.jobs.load_jobs()), 1)

    def test_accept_can_change_default_days(self):
        self.start_offer()
        result = self.request('Sim, mas todos os dias.')
        self.assertEqual(entry.sub.configuration(self.jobs.get_job(result['job_id']))['days'], 'daily')

    def test_decline_persists_and_suppresses_further_offers(self):
        self.start_offer()
        self.assertEqual(self.request('Não, obrigado.')['status'], 'declined')
        for _ in range(3):
            reply = self.request('O que tem no RU II hoje?')
            self.assertNotIn('Você costuma almoçar', reply['text'])
            self.assertNotIn('Quer que eu te mande', reply['text'])
        self.assertEqual(self.jobs.load_jobs(), [])
        self.assertEqual(entry.sub.state.run(self.home / 'pruce/state.json', 'read')['profile']['ru_delivery']['stage'], 'declined')

    def test_offer_not_repeated_while_waiting_for_time(self):
        self.request('O que tem no RU II hoje?')
        self.assertNotIn('Você costuma almoçar', self.request('O que tem no RU II hoje?')['text'])
        self.assertEqual(self.jobs.load_jobs(), [])

    def test_changed_habitual_lunch_requires_consent_before_updating_job(self):
        self.start_offer()
        first = self.request('Sim.')
        proposed = self.request('Agora almoço às 13h.')
        self.assertEqual(proposed['status'], 'awaiting_consent')
        self.assertEqual(entry.sub.configuration(self.jobs.get_job(first['job_id']))['time'], '11:00')
        changed = self.request('Sim.')
        self.assertEqual(changed['job_id'], first['job_id'])
        self.assertEqual(entry.sub.configuration(self.jobs.get_job(first['job_id']))['time'], '12:00')

    def test_cancel_suppresses_offer_and_preserves_preference(self):
        self.request('Me manda o RU II todo dia às 11h.')
        self.request('Me manda o RU II daqui a 5 minutos.')
        self.assertEqual(self.request('Para de me mandar o bandejão')['status'], 'cancelled')
        self.assertEqual(self.jobs.load_jobs(), [])
        self.assertNotIn('Você costuma almoçar', self.request('O que tem no RU II hoje?')['text'])
        profile = entry.sub.state.run(self.home / 'pruce/state.json', 'read')['profile']
        self.assertEqual(profile['preferred_ru'], 'setorial_2')

    def test_unbound_acceptance_creates_nothing(self):
        result = self.request('Sim.')
        self.assertEqual(result['status'], 'clarification')
        self.assertEqual(self.jobs.load_jobs(), [])

    def test_one_off_runner_uses_its_own_ru_and_does_not_replace_recurring(self):
        self.request('Me manda o RU I todo dia às 11h.')
        result = self.request('Me manda o RU II daqui a 5 minutos.')
        key = entry.sub.configuration(self.jobs.get_job(result['job_id']))['key']
        query = Mock(return_value={'status': 'ok', 'items': ['Synthetic'], 'text': 'Only scheduled menu'})
        self.assertEqual(daily.render(self.jobs.load_jobs(), query, once_key=key), 'Only scheduled menu')
        self.assertEqual(query.call_args.kwargs['ru'], 'setorial_2')
        self.assertEqual(len(self.jobs.load_jobs()), 2)


if __name__ == '__main__':
    unittest.main()
