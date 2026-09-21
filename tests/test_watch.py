from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pruce_watch_test', ROOT / 'skills/pruce-watch/scripts/watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

HTML = '''<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"AirPods Pro","offers":{"@type":"Offer","price":"1.899,90","priceCurrency":"BRL"}}</script></head></html>'''
URL = 'https://shop.example/product/airpods'


def sample(price=1899.90, typ='any'):
    return {'id': 'abc', 'url': URL, 'canonical_url': URL, 'name': 'AirPods Pro',
            'merchant': 'shop.example', 'currency': 'BRL', 'initial_price': 1899.90,
            'last_price': price, 'lowest_seen_price': price, 'target_type': typ,
            'target_price': 1600 if typ == 'absolute' else None,
            'target_percentage': 10 if typ == 'percentage' else None,
            'created_at': watch.now(), 'last_checked_at': watch.now(),
            'last_notified_at': None, 'last_alerted_price': None, 'status': 'active',
            'history': [{'at': watch.now(), 'price': price}]}


def page(price):
    return HTML.replace('1.899,90', price)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(patch.object(watch, 'HOME', Path(self.tmp.name)))
        self.enterContext(patch.object(watch, 'STATE', Path(self.tmp.name) / 'pruce/watches.json'))
        safe = ModuleType('tools.url_safety')
        safe.is_safe_url = lambda value: True
        safe.sensitive_query_param_name = lambda value: None
        self.enterContext(patch.dict(sys.modules, {'tools.url_safety': safe}))

    def test_generic_watch_opt_in_baseline_dedupe_quiet_and_cancel(self):
        old = [{'title': 'Estágio UFMG laboratório 2026', 'url': 'https://example.org/jobs/1'}]
        new = old + [{'title': 'Nova bolsa UFMG laboratório 2026', 'url': 'https://example.org/jobs/2'}]
        data = {'action': 'add_watch', 'opt_in': True, 'category': 'estágio',
                'label': 'Estágios UFMG', 'query': 'estágio laboratório UFMG Belo Horizonte'}
        with patch.object(watch, 'sync_job') as cron:
            with self.assertRaises(watch.WatchError):
                watch.manage({**data, 'opt_in': False}, search=lambda _: old)
            created = watch.manage(data, search=lambda _: old)
            self.assertEqual(created['status'], 'active')
            self.assertEqual(watch.manage(data, search=lambda _: old)['status'], 'exists')
            self.assertEqual(len(watch.manage({'action': 'list'})['generic_watches']), 1)
            self.assertEqual(watch.tick('generic', search=lambda _: old), '')
            self.assertIn('Nova bolsa', watch.tick('generic', search=lambda _: new))
            self.assertEqual(watch.tick('generic', search=lambda _: new), '')
            self.assertEqual(watch.manage({'action': 'cancel_watch', 'id': created['id']})['status'], 'cancelled')
            self.assertEqual(watch.tick('generic', search=lambda _: new), '')
            self.assertEqual(cron.call_args.args[:2], ('generic', False))

    def test_generic_search_failure_and_empty_baseline_do_not_alert(self):
        data = {'action': 'add_watch', 'opt_in': True, 'category': 'concurso',
                'label': 'Concurso UFMG', 'query': 'site:ufmg.br concurso 2026'}
        with patch.object(watch, 'sync_job'):
            watch.manage(data, search=lambda _: [])
            self.assertEqual(watch.tick('generic', search=lambda _: (_ for _ in ()).throw(OSError('secret'))), '')
            first = [{'title': 'Edital UFMG 2026 aberto', 'url': 'https://ufmg.br/edital/1'}]
            self.assertEqual(watch.tick('generic', search=lambda _: first), '')
            self.assertEqual(watch.tick('generic', search=lambda _: first), '')

    def test_structured_price_brl_and_metadata(self):
        value = watch.extract_product(HTML, URL)
        self.assertEqual((value['price'], value['currency'], value['name']), (1899.90, 'BRL', 'AirPods Pro'))
        self.assertEqual(watch.money('R$ 1.899,90'), 1899.90)
        self.assertEqual(watch.money('1,899.90'), 1899.90)
        self.assertIsNone(watch.money('indisponível'))

    def test_metadata_and_html_fallback_and_unavailable(self):
        self.assertEqual(watch.extract_product('<meta property="product:price:amount" content="149.90"><meta property="product:price:currency" content="BRL">', URL)['price'], 149.90)
        self.assertEqual(watch.extract_product('<span itemprop="price" content="199.00">R$ 199</span>', URL)['price'], 199)
        self.assertEqual(watch.extract_product('<h1>Book</h1><p class="price_color">£51.77</p>', URL)['price'], 51.77)
        with self.assertRaises(watch.WatchError): watch.extract_product('<div>Preço sob consulta</div>', URL)
        with self.assertRaises(watch.WatchError): watch.extract_product('<span itemprop="price" content="0">', URL)

    def test_price_no_change_and_below_target(self):
        w = sample(typ='absolute')
        self.assertEqual(watch.check_price(w, lambda _: page('1.899,90')), '')
        self.assertEqual(len(w['history']), 1)
        self.assertEqual(watch.check_price(w, lambda _: page('1.750,00')), '')
        self.assertEqual(len(w['history']), 2)
        self.assertIn('R$ 1.590,00', watch.check_price(w, lambda _: page('1.590,00')))
        self.assertEqual(watch.check_price(w, lambda _: page('1.590,00')), '')
        self.assertEqual(w['lowest_seen_price'], 1590)

    def test_any_drop_percentage_and_unique_alert(self):
        w = sample()
        self.assertIn('queda', watch.check_price(w, lambda _: page('1.749,00')))
        self.assertEqual(watch.check_price(w, lambda _: page('1.749,00')), '')
        self.assertEqual(watch.check_price(w, lambda _: page('1.800,00')), '')
        self.assertEqual(watch.check_price(w, lambda _: page('1.760,00')), '')
        self.assertIn('queda', watch.check_price(w, lambda _: page('1.699,00')))
        w = sample(typ='percentage')
        self.assertEqual(watch.check_price(w, lambda _: page('1.720,00')), '')
        self.assertIn('queda', watch.check_price(w, lambda _: page('1.700,00')))

    def test_http_and_changed_html_keep_last_price(self):
        w = sample()
        for fetch in (lambda _: (_ for _ in ()).throw(OSError('HTTP 403')),
                      lambda _: '<html><body>new markup</body></html>'):
            self.assertEqual(watch.check_price(w, fetch), '')
            self.assertEqual(w['last_price'], 1899.90)
            self.assertIsNone(w['last_notified_at'])

    def test_price_persistence_create_edit_list_cancel_restart_isolation(self):
        with patch.object(watch, 'clean_url', return_value=URL), patch.object(watch, 'sync_job') as cron:
            result = watch.manage({'action': 'inspect_price', 'url': URL}, fetch=lambda _: HTML)
            self.assertEqual(result['status'], 'pending')
            self.assertEqual(watch.read_state()['price_watches'][0]['status'], 'pending')
            self.assertEqual(watch.manage({'action': 'set_price', 'target_type': 'absolute', 'target_price': 'R$ 1.600,00'})['status'], 'active')
            self.assertEqual(watch.manage({'action': 'list'})['price_watches'][0]['target_price'], 1600)
            self.assertEqual(watch.manage({'action': 'set_price', 'target_type': 'any'})['status'], 'active')
            self.assertIn('Menor preço', watch.manage({'action': 'price_status'})['text'])
            self.assertEqual(watch.manage({'action': 'cancel_price'})['status'], 'cancelled')
            self.assertEqual(watch.manage({'action': 'list'})['price_watches'], [])
            self.assertEqual(watch.read_state()['price_watches'][0]['status'], 'cancelled')
            self.assertEqual(cron.call_count, 3)
        with tempfile.TemporaryDirectory() as other:
            with patch.object(watch, 'STATE', Path(other) / 'pruce/watches.json'):
                self.assertEqual(watch.read_state()['price_watches'], [])

    def test_news_optin_schedule_edit_pause_resume_cancel(self):
        with patch.object(watch, 'sync_job'), patch.object(watch, 'schedule', return_value='0 11 * * 1,3,5'):
            base = {'action': 'enable_news', 'interests': ['Apple', 'UFMG'], 'timezone': 'America/Sao_Paulo',
                    'schedule': {'mode': 'digest', 'time': '08:00', 'days': [0, 2, 4]}}
            with self.assertRaises(watch.WatchError): watch.manage(base)
            self.assertFalse(watch.read_state()['news']['enabled'])
            self.assertTrue(watch.manage({**base, 'opt_in': True})['news']['enabled'])
            self.assertEqual(watch.read_state()['news']['interests'], ['Apple', 'UFMG'])
            watch.manage({'action': 'update_news', 'interests': ['UFMG', 'Fórmula 1']})
            self.assertEqual(watch.read_state()['news']['interests'], ['UFMG', 'Fórmula 1'])
            watch.manage({'action': 'pause_news'})
            self.assertFalse(watch.read_state()['news']['enabled'])
            watch.manage({'action': 'resume_news'})
            self.assertTrue(watch.read_state()['news']['enabled'])
            watch.manage({'action': 'cancel_news'})
            self.assertEqual(watch.read_state()['news']['interests'], [])

    def test_news_generation_dedupe_repeat_and_no_news(self):
        profile = watch.default_state()['news']
        profile.update(enabled=True, interests=['Apple'], schedule={'mode': 'digest', 'time': '08:00', 'days': 'daily'})
        date = '2026-09-21T10:00:00+00:00'
        a = {'title': 'Apple lança novo modelo de iPhone em setembro', 'url': 'https://news.example/a', 'date': date}
        b = {'title': 'Apple lança novo modelo de iPhone em setembro', 'url': 'https://other.example/b', 'date': date}
        stories = watch.collect_news(profile, lambda _: [a, b], today=datetime.fromisoformat(date))
        self.assertEqual(len(stories), 1)
        profile['delivered'] = [stories[0]['id']]
        profile['delivered_titles'] = [stories[0]['title']]
        self.assertEqual(watch.collect_news(profile, lambda _: [a, b], today=datetime.fromisoformat(date)), [])
        self.assertEqual(watch.collect_news(profile, lambda _: [], today=datetime.fromisoformat(date)), [])
        self.assertEqual(watch.render_news([]), '')

    def test_news_search_failure_silent_and_important_filter(self):
        p = watch.default_state()['news']
        p['interests'] = ['Rush']
        self.assertEqual(watch.collect_news(p, lambda _: (_ for _ in ()).throw(OSError()), important=True), [])
        quiet = {'title': 'Uma curiosidade sobre a banda Rush', 'url': 'https://news.example/quiet', 'date': '2026-09-21T10:00:00Z'}
        self.assertEqual(watch.collect_news(p, lambda _: [quiet], important=True, today=datetime.fromisoformat('2026-09-21T12:00:00+00:00')), [])

    def test_news_send_now_last_story_and_silent_tick(self):
        state = watch.default_state()
        state['news'].update(enabled=True, interests=['UFMG'], schedule={'mode': 'digest', 'time': '08:00', 'days': 'daily'})
        watch.save_state(state)
        self.assertEqual(watch.tick('news', search=lambda _: []), '')
        self.assertIn('Não encontrei', watch.manage({'action': 'send_news'}, search=lambda _: [])['text'])
        self.assertEqual(watch.read_state()['news']['delivered'], [])

    def test_news_send_now_real_result_context_and_repeat(self):
        state = watch.default_state()
        state['news'].update(enabled=True, interests=['Apple'], schedule={'mode': 'digest', 'time': '08:00', 'days': 'daily'})
        watch.save_state(state)
        story = {'title': 'Apple anuncia um novo recurso do iPhone', 'url': 'https://news.example/apple',
                 'date': watch.now()}
        first = watch.manage({'action': 'send_news'}, search=lambda _: [story])
        self.assertIn('Apple anuncia', first['text'])
        self.assertEqual(watch.manage({'action': 'story', 'index': 1})['story']['url'], story['url'])
        self.assertIn('Não encontrei', watch.manage({'action': 'send_news'}, search=lambda _: [story])['text'])
        self.assertEqual(len(watch.read_state()['news']['delivered']), 1)

    def test_important_mode_uses_user_timezone_and_remains_opt_in(self):
        fake_clock = type('Clock', (), {'now': lambda _: datetime(2026, 9, 21, tzinfo=ZoneInfo('UTC'))})()
        with patch.object(watch, 'sync_job') as cron:
            result = watch.manage({'action': 'enable_news', 'opt_in': True,
                'interests': ['Apple'], 'timezone': 'America/Sao_Paulo',
                'schedule': {'mode': 'important'}}, runtime=(None, None, fake_clock))
        self.assertTrue(result['news']['enabled'])
        self.assertEqual(cron.call_args_list[0].args[:3], ('important', True, '29 12,18,0 * * *'))

    def test_timezone_and_clean_url(self):
        fake_clock = type('Clock', (), {'now': lambda _: datetime(2026, 9, 21, tzinfo=ZoneInfo('UTC'))})()
        self.assertEqual(watch.schedule('08:00', [0, 2, 4], 'America/Sao_Paulo', (None, None, fake_clock)), '0 11 * * 1,3,5')
        self.assertEqual(watch.important_schedule('America/Sao_Paulo', (None, None, fake_clock)), '29 12,18,0 * * *')
        self.assertEqual(watch.clean_url('https://SHOP.example/product?utm_source=x&a=b'), 'https://shop.example/product?a=b')
        with self.assertRaises(watch.WatchError): watch.clean_url('http://127.0.0.1/private')


@unittest.skipUnless(Path('/opt/hermes/cron/jobs.py').exists(), 'requires native Hermes scheduler')
class NativeWatchTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, '/opt/hermes')
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        self.enterContext(patch.object(watch, 'HOME', self.home))
        self.enterContext(patch.object(watch, 'STATE', self.home / 'pruce/watches.json'))
        self.jobs, self.scheduler, self.clock = watch.native_runtime()
        self.enterContext(self.jobs.use_cron_store(self.home))
        self.enterContext(patch.object(watch, 'origin_destination', return_value=(
            {'platform': 'imessage', 'chat_id': 'synthetic-owner'}, 'imessage:synthetic-owner')))

    def test_one_job_update_restart_cancel_and_isolation(self):
        runtime = (self.jobs, self.scheduler, self.clock)
        watch.sync_job('price', True, '17 8,14,20 * * *', runtime=runtime)
        first = self.jobs.load_jobs()[0]
        self.assertEqual(first['deliver'], 'imessage:synthetic-owner')
        self.assertTrue(first['no_agent'])
        self.assertTrue((self.home / 'scripts/pruce-price-watch.py').exists())
        watch.sync_job('price', True, '17 8,14,20 * * *', runtime=runtime)
        self.assertEqual([j['id'] for j in self.jobs.load_jobs()], [first['id']])
        watch.sync_job('news', True, '0 11 * * *', runtime=runtime)
        self.assertEqual(len(self.jobs.load_jobs()), 2)
        watch.sync_job('price', False, None, runtime=runtime)
        self.assertEqual([j['name'] for j in self.jobs.load_jobs()], ['pruce-news-digest'])

    def test_no_agent_cron_silent_without_changes(self):
        runtime = (self.jobs, self.scheduler, self.clock)
        watch.sync_job('price', True, '17 8,14,20 * * *', runtime=runtime)
        job = self.jobs.load_jobs()[0]
        with patch.object(self.scheduler, '_run_job_script_with_claim_heartbeat', return_value=(True, '')):
            ok, document, delivered, error = self.scheduler._run_no_agent_job(job, job['id'], 'pruce-price-watch', None)
        self.assertTrue(ok)
        self.assertEqual(delivered, self.scheduler.SILENT_MARKER)

    def test_generic_native_job_is_single_and_cancellable(self):
        runtime = (self.jobs, self.scheduler, self.clock)
        watch.sync_job('generic', True, '41 9,18 * * *', runtime=runtime)
        first = self.jobs.load_jobs()[0]
        self.assertEqual(first['name'], 'pruce-generic-watch')
        self.assertEqual(first['deliver'], 'imessage:synthetic-owner')
        self.assertTrue((self.home / 'scripts/pruce-generic-watch.py').exists())
        watch.sync_job('generic', True, '41 9,18 * * *', runtime=runtime)
        self.assertEqual([j['id'] for j in self.jobs.load_jobs()], [first['id']])
        watch.sync_job('generic', False, None, runtime=runtime)
        self.assertEqual(self.jobs.load_jobs(), [])


if __name__ == '__main__': unittest.main()
