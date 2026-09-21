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


def product_html(name, price, currency='BRL'):
    return ('<script type="application/ld+json">' + json.dumps({
        '@type': 'Product', 'name': name,
        'offers': {'@type': 'Offer', 'price': price, 'priceCurrency': currency}}) + '</script>')


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
                'label': 'Estágios UFMG', 'query': 'estágio laboratório UFMG Belo Horizonte',
                'condition': 'vaga nova com inscrição aberta'}
        with patch.object(watch, 'sync_job') as cron:
            with self.assertRaises(watch.WatchError):
                watch.manage({**data, 'opt_in': False}, search=lambda _: old)
            created = watch.manage(data, search=lambda _: old)
            self.assertEqual(created['status'], 'active')
            stored = watch.manage({'action': 'list'})['generic_watches'][0]
            self.assertEqual(stored['condition'], 'vaga nova com inscrição aberta')
            self.assertEqual(stored['cadence'], 'twice_daily')
            self.assertEqual(stored['last_observation']['outcome'], 'baseline')
            self.assertEqual(len(stored['history']), 1)
            self.assertEqual(watch.manage(data, search=lambda _: old)['status'], 'exists')
            self.assertEqual(len(watch.manage({'action': 'list'})['generic_watches']), 1)
            self.assertEqual(watch.tick('generic', search=lambda _: old), '')
            self.assertIn('Nova bolsa', watch.tick('generic', search=lambda _: new))
            observed = watch.manage({'action': 'list'})['generic_watches'][0]
            self.assertEqual(observed['last_observation']['new_count'], 1)
            self.assertEqual(len(observed['history']), 3)
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
            failed = watch.manage({'action': 'list'})['generic_watches'][0]
            self.assertEqual(failed['last_observation']['outcome'], 'unavailable')
            self.assertTrue(failed['history'])
            first = [{'title': 'Edital UFMG 2026 aberto', 'url': 'https://ufmg.br/edital/1'}]
            self.assertEqual(watch.tick('generic', search=lambda _: first), '')
            self.assertEqual(watch.tick('generic', search=lambda _: first), '')

    def test_legacy_generic_watch_gains_additive_observation_fields(self):
        legacy = {'id': 'old', 'category': 'outro', 'label': 'Release público',
                  'query': 'software release notes', 'status': 'active',
                  'baseline_ready': True, 'seen': [], 'last_notified_at': None}
        self.assertEqual(watch.check_generic(legacy, search=lambda _: []), '')
        self.assertEqual(legacy['condition'], 'novo resultado público que corresponda à busca')
        self.assertEqual(legacy['cadence'], 'twice_daily')
        self.assertEqual(legacy['last_observation']['result_count'], 0)
        self.assertEqual(len(legacy['history']), 1)

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
        self.assertEqual(watch.extract_product('<h1>AirPods Pro 3</h1><script>{"productVariant":{"price":{"amount":2099.9,"currencyCode":"BRL"}}}</script>', URL)['price'], 2099.9)
        self.assertEqual(watch.extract_product('<h1>AirPods Pro 3</h1><script>ShopifyAnalytics.lib.track("Viewed Product",{"currency":"BRL","name":"AirPods Pro 3","price":"2099.90","available":true},undefined)</script>', URL)['price'], 2099.9)
        self.assertEqual(watch.extract_product('<h1>AirPods Pro 3</h1><h2 class="price">R$ 1.599,00 <span>no pix</span></h2>', URL)['price'], 1599)
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

    def test_multistore_discovery_filters_wrong_product_and_duplicates(self):
        self.assertTrue(watch.product_matches('AirPods Pro 3', 'AirPods Pro 3ª Geração - Novo e Lacrado'))
        links = {
            'https://a.example/airpods-pro-3': ('AirPods Pro 3', '1.899,00'),
            'https://b.example/airpods-pro-3': ('Apple AirPods Pro 3', '1.949,00'),
            'https://c.example/airpods-pro-3': ('AirPods Pro 3', '2.099,00'),
            'https://wrong.example/airpods-pro-2': ('AirPods Pro 2', '999,00'),
            'https://accessory.example/case': ('Capa para AirPods Pro 3', '49,00'),
        }
        search = lambda _: [{'url': u, 'title': name} for u, (name, _) in links.items()]
        fetch = lambda u: product_html(*links[u])
        result = watch.manage({'action': 'discover_price', 'query': 'AirPods Pro 3'},
                              fetch=fetch, product_search=search)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual([x['merchant'] for x in result['offers']], ['a.example', 'b.example', 'c.example'])
        self.assertIn('R$ 1.899,00', result['text'])
        self.assertEqual(len(watch.read_state()['price_watches'][0]['offers']), 3)

    def test_multistore_lowest_five_percent_store_switch_and_unavailable(self):
        links = {'https://a.example/p': ('AirPods Pro 3', '1.900,00'),
                 'https://b.example/p': ('AirPods Pro 3', '1.949,00')}
        search = lambda _: [{'url': u, 'title': name} for u, (name, _) in links.items()]
        fetch = lambda u: product_html(*links[u])
        watch.manage({'action': 'discover_price', 'query': 'AirPods Pro 3'}, fetch=fetch, product_search=search)
        with patch.object(watch, 'sync_job'):
            watch.manage({'action': 'select_price', 'selection_mode': 'lowest'})
            watch.manage({'action': 'set_price', 'target_type': 'percentage', 'target_percentage': 5})
        w = watch.read_state()['price_watches'][0]
        self.assertEqual(w['initial_price'], 1900)
        links['https://b.example/p'] = ('AirPods Pro 3', '1.800,00')
        alert = watch.check_price(w, fetch, search)
        self.assertIn('b.example', alert)
        self.assertIn('R$ 1.800,00', alert)
        self.assertEqual(w['last_price'], 1800)
        self.assertEqual(watch.check_price(w, fetch, search), '')
        def one_dead(u):
            if 'a.example' in u: raise OSError('HTTP 404')
            return fetch(u)
        self.assertEqual(watch.check_price(w, one_dead, search), '')
        self.assertEqual([x['status'] for x in w['offers']], ['unavailable', 'available'])
        self.assertEqual(w['status'], 'active')
        self.assertEqual(w['last_price'], 1800)

    def test_multistore_specific_stores_and_no_reliable_offer(self):
        links = {'https://a.example/p': ('MacBook Air M4', '5.900,00'),
                 'https://b.example/p': ('MacBook Air M4', '6.100,00')}
        search = lambda _: [{'url': u, 'title': name} for u, (name, _) in links.items()]
        fetch = lambda u: product_html(*links[u])
        watch.manage({'action': 'discover_price', 'query': 'MacBook Air M4'}, fetch=fetch, product_search=search)
        selected = watch.manage({'action': 'select_price', 'selection_mode': 'stores', 'stores': ['b.example']})
        self.assertEqual(selected['watch']['last_price'], 6100)
        self.assertEqual(len(selected['watch']['selected_offer_ids']), 1)
        no_offer = watch.manage({'action': 'discover_price', 'query': 'AirPods Pro 3'},
                                fetch=lambda _: product_html('AirPods Pro 2', '999,00'),
                                product_search=lambda _: [{'url': 'https://wrong.example/p', 'title': 'AirPods Pro 3'}])
        self.assertEqual(no_offer['status'], 'unavailable')
        self.assertEqual(len(watch.read_state()['price_watches']), 1)

    def test_multistore_discovers_new_store_once_per_72_hours(self):
        first = 'https://a.example/p'
        second = 'https://b.example/p'
        pages = {first: product_html('AirPods Pro 3', '1.900,00'),
                 second: product_html('AirPods Pro 3', '1.700,00')}
        watch.manage({'action': 'discover_price', 'query': 'AirPods Pro 3'},
                     fetch=lambda u: pages[u],
                     product_search=lambda _: [{'url': first, 'title': 'AirPods Pro 3'}])
        with patch.object(watch, 'sync_job'):
            watch.manage({'action': 'select_price', 'selection_mode': 'lowest'})
            watch.manage({'action': 'set_price', 'target_type': 'any'})
        w = watch.read_state()['price_watches'][0]
        w['last_discovery_at'] = '2020-01-01T00:00:00+00:00'
        searches = []
        def search(query):
            searches.append(query)
            return [{'url': second, 'title': 'AirPods Pro 3'}]
        self.assertIn('b.example', watch.check_price(w, lambda u: pages[u], search))
        self.assertEqual(len(w['offers']), 2)
        self.assertEqual(watch.check_price(w, lambda u: pages[u], search), '')
        self.assertEqual(len(searches), 1)

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

    def test_news_balances_three_interests_and_caps_six(self):
        profile = watch.default_state()['news']
        profile['interests'] = ['Apple', 'inteligência artificial', 'UFMG']
        date = '2026-09-21T10:00:00+00:00'
        subjects = ['novos aparelhos para estudantes', 'relatório financeiro trimestral',
                    'parceria acadêmica internacional', 'festival cultural de setembro',
                    'atualização inédita de software', 'pesquisa sobre baterias sustentáveis',
                    'expansão de laboratório regional', 'programa de bolsas científicas']
        def search(query):
            topic = 'Apple' if 'Apple' in query else 'IA' if 'inteligência' in query else 'UFMG'
            count = 8 if topic == 'Apple' else 3
            detail = {'Apple': 'iphone ios', 'IA': 'algoritmos modelos', 'UFMG': 'campus universidade'}[topic]
            return [{'title': f'{topic} {detail} divulga {subjects[i]}',
                     'url': f'https://{topic.lower()}.example/{i}', 'date': date} for i in range(count)]
        stories = watch.collect_news(profile, search, today=datetime.fromisoformat(date))
        self.assertEqual(len(stories), 6)
        self.assertEqual([sum(s['interest'] == topic for s in stories) for topic in profile['interests']], [2, 2, 2])
        self.assertEqual([s['interest'] for s in stories[:3]], profile['interests'])

    def test_news_topic_without_content_redistributes_and_explains(self):
        profile = watch.default_state()['news']
        profile['interests'] = ['Apple', 'IA', 'UFMG']
        date = '2026-09-21T10:00:00+00:00'
        subjects = ['novos aparelhos para estudantes', 'relatório financeiro trimestral',
                    'parceria acadêmica internacional', 'festival cultural de setembro',
                    'atualização inédita de software']
        def search(query):
            if 'UFMG' in query: return []
            topic = 'Apple' if 'Apple' in query else 'IA'
            detail = {'Apple': 'iphone ios', 'IA': 'algoritmos modelos'}[topic]
            return [{'title': f'{topic} {detail} divulga {subjects[i]}',
                     'url': f'https://{topic.lower()}.example/{i}', 'date': date} for i in range(5)]
        stories = watch.collect_news(profile, search, today=datetime.fromisoformat(date))
        self.assertEqual(len(stories), 6)
        self.assertEqual({s['interest'] for s in stories}, {'Apple', 'IA'})
        self.assertIn('Sem novidade recente e verificável sobre UFMG', watch.render_news(stories, profile['interests']))

    def test_rss_direct_canonical_url_and_google_fallback(self):
        rss = 'https://news.google.com/rss/articles/example'
        item = {'title': 'Apple anuncia novo iPhone em evento oficial - Canaltech',
                'url': rss, 'source': 'Canaltech', 'source_url': 'https://canaltech.com.br',
                'date': '2026-09-21T10:00:00+00:00'}
        direct = 'https://canaltech.com.br/smartphone/apple-anuncia-novo-iphone-em-evento-oficial/'
        lookup = lambda _: [{'url': direct, 'title': 'Apple anuncia novo iPhone em evento oficial'}]
        self.assertEqual(watch.resolve_rss_story(item, lookup), direct)
        self.assertIsNone(watch.resolve_rss_story(item, lambda _: []))
        profile = watch.default_state()['news']
        profile['interests'] = ['Apple']
        fixed = datetime.fromisoformat('2026-09-21T12:00:00+00:00')
        resolved = watch.collect_news(profile, lambda _: [item], today=fixed, resolve=lambda _: direct)
        self.assertEqual(resolved[0]['url'], direct)
        fallback = watch.collect_news(profile, lambda _: [item], today=fixed, resolve=lambda _: None)
        self.assertEqual(fallback[0]['url'], rss)

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
