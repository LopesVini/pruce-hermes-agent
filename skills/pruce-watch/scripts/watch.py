"""Persistent price and news watches using the native Hermes cron provider."""
import fcntl
import hashlib
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

LOG = logging.getLogger("pruce.watch")
HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes"))
STATE = HOME / "pruce/watches.json"
JOBS = {"price": ("pruce-price-watch", "pruce-price-watch.py", "pruce_price_v1"),
        "news": ("pruce-news-digest", "pruce-news-digest.py", "pruce_news_v1"),
        "important": ("pruce-news-important", "pruce-news-important.py", "pruce_news_important_v1"),
        "generic": ("pruce-generic-watch", "pruce-generic-watch.py", "pruce_generic_v1")}
CATEGORIES = {"produto", "passagem", "evento", "ingresso", "concurso", "vaga",
              "imóvel", "carro", "lançamento", "bolsa", "estágio", "hackathon", "outro"}


class WatchError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_url(raw):
    from tools.url_safety import is_safe_url, sensitive_query_param_name
    if not isinstance(raw, str) or len(raw) > 2048:
        raise WatchError("Envie um link público do produto.")
    p = urlsplit(raw.strip())
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise WatchError("Preciso de um link HTTPS público da loja.")
    if sensitive_query_param_name(raw) or not is_safe_url(raw):
        raise WatchError("Esse link não é seguro para consulta automática.")
    query = [(k, v) for k, v in parse_qsl(p.query) if not re.match(r"^(utm_|fbclid$|gclid$)", k, re.I)]
    return urlunsplit(("https", p.netloc.lower(), p.path or "/", urlencode(query), ""))


def fetch_page(url):
    from tools.url_safety import create_ssrf_safe_client
    with create_ssrf_safe_client(timeout=8.0, follow_redirects=False) as client:
        response = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PrucePriceWatch/1.0)",
                                            "Accept": "text/html,application/xhtml+xml"})
        if response.status_code != 200:
            raise WatchError("Não consegui acompanhar automaticamente o preço nessa loja ainda.")
        if "html" not in response.headers.get("content-type", "").lower():
            raise WatchError("A loja não forneceu uma página de produto legível.")
        if len(response.content) > 2_000_000:
            raise WatchError("A página da loja é grande demais para leitura segura.")
        return response.text


def money(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    elif isinstance(value, str):
        s = re.sub(r"[^\d,.-]", "", value.strip())
        if not s:
            return None
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s:
            s = s.replace(".", "").replace(",", ".") if len(s.rsplit(",", 1)[-1]) <= 2 else s.replace(",", "")
        elif s.count(".") == 1 and len(s.rsplit(".", 1)[-1]) == 3:
            s = s.replace(".", "")
        try:
            number = float(s)
        except ValueError:
            return None
    else:
        return None
    return round(number, 2) if 0 < number < 100_000_000 else None


class ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.ld, self.title, self.heading, self._script, self._title, self._heading = {}, [], "", "", False, False, False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            self.meta[key] = attrs.get("content", "")
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._script = True
            self.ld.append("")
        if tag == "title":
            self._title = True
        if tag == "h1":
            self._heading = True

    def handle_endtag(self, tag):
        if tag == "script": self._script = False
        if tag == "title": self._title = False
        if tag == "h1": self._heading = False

    def handle_data(self, data):
        if self._script and self.ld: self.ld[-1] += data
        if self._title: self.title += data
        if self._heading: self.heading += data


def extract_product(html, url):
    page = ProductHTML()
    page.feed(html[:2_000_000])
    candidates = []
    def visit(obj):
        if isinstance(obj, list):
            for x in obj: visit(x)
        elif isinstance(obj, dict):
            kind = obj.get("@type", "")
            if isinstance(kind, list): kind = " ".join(kind)
            if "Product" in str(kind):
                offers = obj.get("offers", {})
                if isinstance(offers, list): offers = next((x for x in offers if isinstance(x, dict) and money(x.get("price"))), {})
                if isinstance(offers, dict):
                    specification = offers.get("priceSpecification", {})
                    if isinstance(specification, list):
                        specification = next((x for x in specification if isinstance(x, dict) and money(x.get("price"))), {})
                    if not isinstance(specification, dict): specification = {}
                    price = money(offers.get("price") or offers.get("lowPrice") or specification.get("price"))
                    if price: candidates.append((price, offers.get("priceCurrency") or specification.get("priceCurrency"), obj.get("name")))
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in obj: visit(obj[key])
    for raw in page.ld:
        try: visit(json.loads(raw))
        except (ValueError, TypeError): pass
    meta = page.meta
    if not candidates:
        for key in ("product:price:amount", "og:price:amount", "price", "twitter:data1"):
            value = money(meta.get(key))
            if value:
                candidates.append((value, meta.get("product:price:currency") or meta.get("og:price:currency"), None))
                break
    if not candidates:
        # Conservative visible HTML fallback: only explicitly labelled price attributes.
        match = re.search(r'(?:itemprop=["\']price["\'][^>]{0,200}content=["\']|data-price=["\'])([\d.,]+)', html, re.I)
        if match and money(match.group(1)):
            candidates.append((money(match.group(1)), meta.get("product:price:currency"), None))
    if not candidates:
        match = re.search(r'<[^>]{0,200}class=["\'][^"\']*\bprice_color\b[^"\']*["\'][^>]*>\s*([£€$]|R\$)\s*([\d.,]+)', html, re.I)
        if match and money(match.group(2)):
            candidates.append((money(match.group(2)), {"£": "GBP", "€": "EUR", "$": "USD", "R$": "BRL"}[match.group(1)], None))
    if not candidates:
        match = re.search(r'"productVariant"\s*:\s*\{\s*"price"\s*:\s*\{\s*"amount"\s*:\s*([\d.]+)\s*,\s*"currencyCode"\s*:\s*"([A-Z]{3})"', html)
        if match and money(match.group(1)) and page.heading:
            candidates.append((money(match.group(1)), match.group(2), page.heading))
    if not candidates:
        match = re.search(r'Viewed Product"\s*,\s*(\{.{0,1500}?\})\s*,\s*undefined', html, re.S)
        if match:
            try:
                event = json.loads(match.group(1))
                if event.get("available") is True and money(event.get("price")):
                    candidates.append((money(event["price"]), event.get("currency"), event.get("name") or page.heading))
            except (ValueError, TypeError, KeyError): pass
    if not candidates:
        match = re.search(r'<h[1-6][^>]{0,200}class=["\'][^"\']*\bprice\b[^"\']*["\'][^>]*>\s*(R\$|[£€$])\s*([\d.,]+)', html, re.I)
        if match and money(match.group(2)) and page.heading:
            candidates.append((money(match.group(2)), {"R$": "BRL", "£": "GBP", "€": "EUR", "$": "USD"}[match.group(1)], page.heading))
    if not candidates:
        raise WatchError("Não consegui acompanhar automaticamente o preço nessa loja ainda.")
    price, currency, name = candidates[0]
    currency = (currency or ("BRL" if "R$" in html else "")).upper()
    if currency not in {"BRL", "USD", "EUR", "GBP"}:
        raise WatchError("Encontrei um valor, mas não consegui confirmar a moeda.")
    return {"name": unescape(str(name or meta.get("og:title") or page.heading or page.title)).strip()[:180],
            "merchant": urlsplit(url).hostname, "currency": currency, "price": price}


def product_tokens(value):
    value = re.sub(r"(?<=\d)[ªº]", "", str(value).casefold())
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    stop = {"a", "o", "de", "do", "da", "dos", "das", "um", "uma", "para", "por",
            "preco", "produto", "comprar", "acompanhar", "acompanhe", "olho", "fica",
            "apple", "fone", "ouvido", "geracao", "novo", "original", "lacrado"}
    return [token for token in re.findall(r"[a-z0-9]+", value) if token not in stop]


def product_matches(query, name):
    wanted = set(product_tokens(query))
    found = set(product_tokens(name))
    if not wanted or not wanted <= found:
        return False
    # A matching device name in an accessory listing is still the wrong item.
    accessory = {"capa", "case", "capinha", "protetor", "pelicula", "cabo",
                 "carregador", "suporte", "compativel", "replica", "clone", "peca"}
    return not bool(accessory & found)


def search_products(query):
    """Official Hermes search first; a bounded public RSS search is a fallback."""
    from tools.web_tools import web_search_tool
    try:
        result = json.loads(web_search_tool(query, limit=12))
        if result.get("success") and result.get("data", {}).get("web"):
            return result["data"]["web"][:12]
    except Exception:
        pass
    from tools.url_safety import create_ssrf_safe_client
    url = "https://www.bing.com/search?" + urlencode({"format": "rss", "q": query[:160]})
    with create_ssrf_safe_client(timeout=8.0, follow_redirects=False) as client:
        response = client.get(url, headers={"User-Agent": "PrucePriceWatch/1.0"})
        response.raise_for_status()
        if len(response.content) > 500_000: raise WatchError("Pesquisa de ofertas grande demais.")
    root = ElementTree.fromstring(response.content)
    return [{"title": item.findtext("title") or "", "url": item.findtext("link") or ""}
            for item in root.findall("./channel/item")[:12]]


def discover_offers(query, fetch=fetch_page, search=search_products, max_checks=10, extra_query=True):
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120 or not product_tokens(query):
        raise WatchError("Qual é o nome exato do produto que você quer acompanhar?")
    query = query.strip()
    offers, seen_urls, checked, seen_domains, domain_attempts = [], set(), 0, set(), {}
    searches = [f'"{query}" loja independente comprar Brasil']
    if extra_query:
        searches.extend((f'"{query}" comprar preço Brasil site:com.br',
                         f'"{query}" comprar preço Brasil'))
    for search_index, search_query in enumerate(searches):
        checked_this_search = 0
        search_budget = max_checks if len(searches) == 1 else max(2, max_checks // 3 + (search_index == 0))
        try: results = search(search_query)
        except Exception as error:
            LOG.warning("product_search_error query_hash=%s type=%s", hashlib.sha256(query.encode()).hexdigest()[:10], type(error).__name__)
            continue
        for result in results[:12]:
            if checked >= max_checks or checked_this_search >= search_budget: break
            try: url = clean_url(result.get("url") or result.get("href"))
            except (WatchError, ValueError, TypeError): continue
            domain = urlsplit(url).hostname.removeprefix("www.")
            if any(domain == excluded or domain.endswith("." + excluded) for excluded in
                   ("buscape.com.br", "zoom.com.br", "promobit.com.br", "reclameaqui.com.br",
                    "jacotei.com.br", "busqa.com.br")):
                continue
            if url in seen_urls or domain_attempts.get(domain, 0) >= 3: continue
            # Search snippets are candidate discovery only, never price evidence.
            title = result.get("title") or ""
            if not product_matches(query, title): continue
            if re.search(r"\b(?:review|revis[aã]o|comparativo|compare|versus|guia|not[ií]cias|melhores)\b|\s+vs\.?\s+", title, re.I):
                continue
            seen_urls.add(url)
            domain_attempts[domain] = domain_attempts.get(domain, 0) + 1
            checked += 1
            checked_this_search += 1
            try:
                product = extract_product(fetch(url), url)
                if not product_matches(query, product["name"]): continue
                if (domain, product["currency"]) in seen_domains: continue
            except Exception as error:
                LOG.info("offer_read_unavailable domain_hash=%s type=%s", hashlib.sha256(domain.encode()).hexdigest()[:10], type(error).__name__)
                continue
            offers.append({"id": hashlib.sha256(url.encode()).hexdigest()[:12], "url": url,
                           "name": product["name"], "merchant": domain,
                           "currency": product["currency"], "initial_price": product["price"],
                           "last_price": product["price"], "status": "available",
                           "last_checked_at": now()})
            seen_domains.add((domain, product["currency"]))
        if len(offers) >= 3 or checked >= max_checks: break
    if not offers: return []
    # Prices in different currencies cannot be compared as a single minimum.
    currency = "BRL" if any(o["currency"] == "BRL" for o in offers) else offers[0]["currency"]
    offers = [o for o in offers if o["currency"] == currency]
    return sorted(offers, key=lambda o: (o["last_price"], o["merchant"]))[:6]


def default_state():
    return {"version": 1, "price_watches": [], "generic_watches": [], "news": {"enabled": False, "interests": [],
            "schedule": None, "timezone": None, "last_digest_at": None, "delivered": [],
            "delivered_titles": [], "last_stories": []}}


def read_state():
    if not STATE.exists(): return default_state()
    value = json.loads(STATE.read_text())
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("price_watches"), list) or not isinstance(value.get("news"), dict):
        raise WatchError("O estado dos acompanhamentos precisa de revisão.")
    return value


def save_state(value):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=STATE.parent, delete=False) as output:
        json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
        path = Path(output.name)
    path.chmod(0o600)
    os.replace(path, STATE)


class locked:
    def __enter__(self):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        self.file = (STATE.parent / "watches.lock").open("a")
        fcntl.flock(self.file, fcntl.LOCK_EX)
        return read_state()

    def __exit__(self, *_):
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


def format_price(value, currency):
    symbol = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}[currency]
    return f"{symbol} {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def find_watch(state, selector):
    active = [w for w in state["price_watches"] if w["status"] != "cancelled"]
    if not selector and len(active) == 1: return active[0]
    matches = [w for w in active if selector and (selector.lower() in w["name"].lower() or selector == w["id"])]
    if len(matches) != 1: raise WatchError("Qual produto? Envie o nome ou peça a lista dos acompanhamentos.")
    return matches[0]


def origin_destination():
    from tools.cronjob_job_args import _origin_from_env
    from gateway.session_context import get_session_env
    if get_session_env("HERMES_SESSION_CHAT_TYPE", "") not in ("", "dm", "private", "direct"):
        raise WatchError("Configure acompanhamentos na conversa privada.")
    origin = _origin_from_env()
    if not origin or not re.fullmatch(r"[a-z][a-z0-9_-]*", origin.get("platform", "")) or not re.fullmatch(r"[^\s,:]+", str(origin.get("chat_id", ""))):
        raise WatchError("Não consegui identificar esta conversa para avisos proativos.")
    dest = f"{origin['platform']}:{origin['chat_id']}"
    if origin.get("thread_id"): dest += f":{origin['thread_id']}"
    return origin, dest


def native_runtime():
    sys.path.insert(0, "/opt/hermes")
    from cron import jobs, scheduler
    import hermes_time
    return jobs, scheduler, hermes_time


def config(job, kind):
    name, script, marker = JOBS[kind]
    try:
        data = json.loads(job.get("prompt", ""))
        return data if (job.get("name"), job.get("script"), data.get("kind")) == (name, script, marker) else None
    except (TypeError, ValueError, AttributeError): return None


def install_runner(kind):
    directory = HOME / "scripts"
    directory.mkdir(parents=True, exist_ok=True)
    code = ("import os,runpy\nfrom pathlib import Path\n"
            f"runpy.run_path(str(Path(os.environ.get('HERMES_HOME','/var/lib/hermes'))/'skills/pruce-watch/scripts/watch.py'),run_name='__main__')\n")
    # Runner action is fixed in the managed job's prompt, read by this script.
    code = "import sys\nsys.argv=['watch.py','tick','" + kind + "']\n" + code
    path = directory / JOBS[kind][1]
    with tempfile.NamedTemporaryFile("w", dir=directory, delete=False) as out:
        out.write(code)
        temp = Path(out.name)
    temp.chmod(0o644)
    os.replace(temp, path)


def sync_job(kind, enabled, schedule, destination=None, runtime=None):
    jobs, scheduler, clock = runtime or native_runtime()
    managed = [j for j in jobs.list_jobs(include_disabled=True) if config(j, kind)]
    if not enabled:
        for job in managed: jobs.remove_job(job["id"])
        scheduler._notify_provider_jobs_changed()
        return
    origin, current_dest = origin_destination()
    deliver = managed[0].get("deliver") if managed else (destination or current_dest)
    if not isinstance(deliver, str) or deliver.split(":")[0] in ("local", "all", "origin"):
        raise WatchError("Não consegui confirmar o destino dos avisos.")
    install_runner(kind)
    name, script, marker = JOBS[kind]
    payload = {"name": name, "script": script, "prompt": json.dumps({"kind": marker, "opt_in": True}),
               "no_agent": True, "deliver": deliver, "failure_deliver": "local"}
    if managed:
        result = jobs.update_job(managed[0]["id"], {**payload, "schedule": jobs.parse_schedule(schedule)})
        if not result: raise WatchError("Não consegui atualizar o agendamento.")
        if not result.get("enabled", True): result = jobs.resume_job(result["id"])
        from cron.scheduler_provider import resolve_cron_scheduler
        resolve_cron_scheduler().register_job(result)
    else:
        scheduler.create_job_with_scheduler_registration(**payload, schedule=schedule, origin=origin)
    for duplicate in managed[1:]: jobs.remove_job(duplicate["id"])
    scheduler._notify_provider_jobs_changed()


def schedule(at, days, user_zone, runtime=None):
    _, _, clock = runtime or native_runtime()
    scheduler_zone = clock.now().tzinfo
    zone = ZoneInfo(user_zone)
    hour, minute = map(int, at.split(":"))
    signatures = set()
    for i in range(400):
        day = (datetime.now(timezone.utc).astimezone(zone) + timedelta(days=i)).date()
        local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
        target = local.astimezone(scheduler_zone)
        signatures.add((target.hour, target.minute, (target.date() - day).days))
    if len(signatures) != 1: raise WatchError("Não consigo garantir esse horário no fuso informado.")
    h, m, shift = signatures.pop()
    daypart = "*" if days == "daily" else ",".join(str((d + 1 + shift) % 7) for d in days)
    return f"{m} {h} * * {daypart}"


def important_schedule(user_zone, runtime=None):
    parts = [schedule(f"{hour:02d}:29", "daily", user_zone, runtime).split() for hour in (9, 15, 21)]
    if len({part[0] for part in parts}) != 1:
        raise WatchError("Não consigo garantir horários de verificação nesse fuso.")
    return f"{parts[0][0]} {','.join(part[1] for part in parts)} * * *"


def selected_offers(watch):
    offers = watch.get("offers", [])
    if watch.get("selection_mode") == "stores":
        selected = set(watch.get("selected_offer_ids", []))
        return [offer for offer in offers if offer["id"] in selected]
    return offers


def check_multi_price(watch, fetch=fetch_page, search=search_products):
    previous = watch["last_price"]
    for offer in selected_offers(watch):
        try:
            product = extract_product(fetch(offer["url"]), offer["url"])
            if product["currency"] != watch["currency"] or not product_matches(watch["query"], product["name"]):
                raise WatchError("A página deixou de corresponder ao produto acompanhado.")
            offer["last_price"] = product["price"]
            offer["status"] = "available"
        except Exception as error:
            offer["status"] = "unavailable"
            LOG.warning("price_offer_unavailable watch=%s offer=%s type=%s", watch["id"], offer["id"], type(error).__name__)
        offer["last_checked_at"] = now()
    last_discovery = watch.get("last_discovery_at")
    try:
        old = datetime.fromisoformat(last_discovery) if last_discovery else datetime.min.replace(tzinfo=timezone.utc)
    except ValueError:
        old = datetime.min.replace(tzinfo=timezone.utc)
    if (watch.get("selection_mode") != "stores" and datetime.now(timezone.utc) - old >= timedelta(hours=72)
            and len(watch["offers"]) < 6):
        watch["last_discovery_at"] = now()  # also rate-limits failed discovery
        try:
            discovered = discover_offers(watch["query"], fetch, search, max_checks=6, extra_query=False)
            known = {offer["id"] for offer in watch["offers"]}
            merchants = {offer["merchant"] for offer in watch["offers"]}
            for offer in discovered:
                if offer["id"] not in known and offer["merchant"] not in merchants and offer["currency"] == watch["currency"]:
                    watch["offers"].append(offer)
                    known.add(offer["id"])
                    merchants.add(offer["merchant"])
                    if len(watch["offers"]) >= 6: break
        except Exception as error:
            LOG.warning("price_discovery_error watch=%s type=%s", watch["id"], type(error).__name__)
    available = [offer for offer in selected_offers(watch) if offer["status"] == "available"]
    watch["last_checked_at"] = now()
    if not available:
        LOG.info("price_check watch=%s offers_available=0 alert=False", watch["id"])
        return ""
    cheapest = min(available, key=lambda offer: offer["last_price"])
    price = cheapest["last_price"]
    if price != previous:
        watch["last_price"] = price
        watch["lowest_seen_price"] = min(price, watch["lowest_seen_price"])
        watch["history"].append({"at": watch["last_checked_at"], "price": price,
                                 "offer_id": cheapest["id"]})
        watch["history"] = watch["history"][-100:]
    watch["url"], watch["canonical_url"], watch["merchant"] = cheapest["url"], cheapest["url"], cheapest["merchant"]
    typ = watch["target_type"]
    meets = price < previous and ((typ == "any") or
        (typ == "absolute" and price <= watch["target_price"]) or
        (typ == "percentage" and price <= watch["initial_price"] * (1 - watch["target_percentage"] / 100)))
    meets = meets and (watch.get("last_alerted_price") is None or price < watch["last_alerted_price"])
    LOG.info("price_check watch=%s previous=%s current=%s offers_available=%d alert=%s",
             watch["id"], previous, price, len(available), meets)
    if not meets: return ""
    watch["last_notified_at"] = now()
    watch["last_alerted_price"] = price
    pct = (previous - price) / previous * 100
    return (f"👀 {watch['name']} caiu.\nMenor preço entre as lojas: "
            f"{format_price(previous, watch['currency'])} → {format_price(price, watch['currency'])} "
            f"(queda de {pct:.1f}%).\n{cheapest['merchant']}: {cheapest['url']}")


def check_price(watch, fetch=fetch_page, search=search_products):
    if watch.get("offers") is not None:
        return check_multi_price(watch, fetch, search)
    previous = watch["last_price"]
    try:
        result = extract_product(fetch(watch["url"]), watch["url"])
        if result["currency"] != watch["currency"]: raise WatchError("Moeda da loja mudou.")
    except Exception as error:
        LOG.warning("price_read_error watch=%s type=%s", watch["id"], type(error).__name__)
        watch["last_checked_at"] = now()
        return ""
    price = result["price"]
    watch["last_checked_at"] = now()
    if price != previous:
        watch["last_price"] = price
        watch["lowest_seen_price"] = min(price, watch["lowest_seen_price"])
        watch["history"].append({"at": watch["last_checked_at"], "price": price})
        watch["history"] = watch["history"][-100:]
    typ = watch["target_type"]
    meets = price < previous and ((typ == "any") or
        (typ == "absolute" and price <= watch["target_price"]) or
        (typ == "percentage" and price <= watch["initial_price"] * (1 - watch["target_percentage"] / 100)))
    # A condition can remain true for many checks; only a new lower price alerts.
    meets = meets and (watch.get("last_alerted_price") is None or price < watch["last_alerted_price"])
    LOG.info("price_check watch=%s previous=%s current=%s alert=%s", watch["id"], previous, price, meets)
    if not meets: return ""
    watch["last_notified_at"] = now()
    watch["last_alerted_price"] = price
    pct = (previous - price) / previous * 100
    return (f"👀 {watch['name']} caiu.\n{format_price(previous, watch['currency'])} → "
            f"{format_price(price, watch['currency'])} (queda de {pct:.1f}%).\n{watch['url']}\n"
            "Quer que eu veja se apareceu mais barato em outras lojas também?")


def canonical_story(url):
    try: return clean_url(url)
    except WatchError: return None


def story_key(title):
    tokens = re.findall(r"\w+", title.lower())
    stop = {"de", "do", "da", "o", "a", "em", "and", "the", "for", "com", "para", "sobre", "new"}
    return set(t for t in tokens if len(t) > 3 and t not in stop)


def same_event(left, right):
    shared = len(left & right)
    return shared >= 4 and shared / max(1, min(len(left), len(right))) >= .7


def search_news(query):
    from tools.web_tools import web_search_tool
    try:
        result = json.loads(web_search_tool(query, limit=6))
        if result.get("success") and any(x.get("published_date") or x.get("published") or x.get("date") for x in result.get("data", {}).get("web", [])):
            return result["data"]["web"]
    except Exception:
        pass
    # Public RSS is a bounded, dated fallback when a new cloud install has no
    # web-search credential or the managed provider is temporarily unavailable.
    from tools.url_safety import create_ssrf_safe_client
    rss_url = "https://news.google.com/rss/search?" + urlencode({
        "q": query[:160], "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})
    with create_ssrf_safe_client(timeout=8.0, follow_redirects=False) as client:
        response = client.get(rss_url, headers={"User-Agent": "PruceNews/1.0"})
        response.raise_for_status()
        if len(response.content) > 1_000_000: raise WatchError("Feed de notícias grande demais")
    root = ElementTree.fromstring(response.content)
    results = []
    for item in root.findall("./channel/item")[:12]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        date = item.findtext("pubDate") or ""
        source = item.find("source")
        try: published = parsedate_to_datetime(date).isoformat()
        except (TypeError, ValueError): continue
        results.append({"title": title, "url": link, "published_date": published,
                        "source": source.text if source is not None else "Google Notícias",
                        "source_url": source.get("url") if source is not None else None})
    return results


def search_web(query):
    from tools.web_tools import web_search_tool
    result = json.loads(web_search_tool(query, limit=12))
    if not result.get("success"):
        raise WatchError("A busca web não está disponível nesta instalação agora.")
    return result.get("data", {}).get("web", [])


def resolve_rss_story(story, lookup=None):
    """One bounded title lookup for a direct publisher URL; RSS link remains fallback."""
    rss_url = story["url"]
    if urlsplit(rss_url).hostname != "news.google.com": return None
    publisher = story.get("source_url")
    if not publisher: return None
    try: publisher_host = urlsplit(publisher).hostname.removeprefix("www.")
    except (ValueError, AttributeError): return None
    if not publisher_host: return None
    if lookup is None:
        from tools.web_tools import web_search_tool
        def lookup(query):
            result = json.loads(web_search_tool(query, limit=4))
            return result.get("data", {}).get("web", []) if result.get("success") else []
    title = re.sub(r"\s+-\s+[^-]{2,60}$", "", story["title"]).strip()
    try: results = lookup(f'"{title[:110]}" site:{publisher_host}')
    except Exception: return None
    wanted = story_key(title)
    for result in results[:4]:
        try: direct = canonical_story(result.get("url") or result.get("href"))
        except (TypeError, ValueError): continue
        if not direct: continue
        host = urlsplit(direct).hostname.removeprefix("www.")
        if host != publisher_host and not host.endswith("." + publisher_host): continue
        found = story_key(result.get("title") or "")
        overlap = len(wanted & found)
        if overlap >= min(3, len(wanted)) and overlap / max(1, min(len(wanted), len(found))) >= .6:
            return direct
    return None


def collect_news(profile, search=search_news, important=False, today=None, resolve=resolve_rss_story):
    today = today or datetime.now(timezone.utc)
    candidates, seen, stories, sources = {}, set(profile["delivered"]), [], set()
    old_events = [story_key(title) for title in profile.get("delivered_titles", [])]
    for interest in profile["interests"][:8]:
        candidates[interest] = []
        query = f"{interest} universidade -Flamengo -futebol when:2d" if interest.casefold() == "ufmg" else f"{interest} when:2d"
        try: results = search(query)
        except Exception as error:
            LOG.warning("news_search_error interest_hash=%s type=%s", hashlib.sha256(interest.encode()).hexdigest()[:10], type(error).__name__)
            continue
        for item in results[:8]:
            url = canonical_story(item.get("url") or item.get("href"))
            title = str(item.get("title") or "").strip()
            if not url or len(title) < 15 or url in seen or any(same_event(story_key(title), old) for old in old_events): continue
            if interest.casefold() == "ufmg" and re.search(r"Flamengo|futebol|Brasileirão|campeonato", title, re.I): continue
            published = item.get("published_date") or item.get("published") or item.get("date")
            if not published: continue  # no reliable recency evidence
            try:
                dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                if not 0 <= (today - dt).total_seconds() <= 72 * 3600: continue
            except ValueError: continue
            if important and not re.search(r"anunci|lanç|aprova|elei|morre|crise|acord|record|announce|launch|release|wins|dies", title, re.I):
                continue
            candidates[interest].append({"id": url, "title": title[:180], "url": url, "interest": interest,
                               "source": item.get("source") or urlsplit(url).hostname,
                               "source_url": item.get("source_url"),
                               "published": dt.date().isoformat(), "tokens": story_key(title)})
            sources.add(str(item.get("source") or urlsplit(url).hostname))
    duplicates = 0
    offsets = {interest: 0 for interest in candidates}
    def take_one(interest):
        nonlocal duplicates
        queue = candidates[interest]
        while offsets[interest] < len(queue):
            item = queue[offsets[interest]]
            offsets[interest] += 1
            if item["id"] in seen or any(same_event(item["tokens"], other["tokens"]) for other in stories):
                duplicates += 1
                continue
            stories.append(item)
            return True
        return False
    # First reserve one place per interest that has a distinct recent story.
    for interest in candidates:
        if len(stories) >= 6: break
        take_one(interest)
    # Fill the remainder in relevance order within each interest, one round at
    # a time, redistributing places when a topic has no usable story.
    while len(stories) < 6:
        progressed = False
        for interest in candidates:
            if len(stories) >= 6: break
            progressed = take_one(interest) or progressed
        if not progressed: break
    for item in stories:
        if item.get("source_url") and urlsplit(item["url"]).hostname == "news.google.com":
            try: direct = resolve(item)
            except Exception: direct = None
            if direct:
                item["id"], item["url"] = direct, direct
    interest_hashes = [hashlib.sha256(value.encode()).hexdigest()[:10] for value in profile["interests"][:8]]
    LOG.info("news_check interest_hashes=%s sources=%d candidates=%d deduplicated=%d sent=%d", interest_hashes, len(sources), sum(map(len, candidates.values())), duplicates, len(stories))
    for item in stories:
        item.pop("tokens", None)
        item.pop("source_url", None)
    return stories


def render_news(stories, interests=None):
    if not stories: return ""
    lines = ["☕ Seu Prucê de hoje"]
    for i, story in enumerate(stories, 1):
        lines.append(f"{i}. {story['interest'].upper()} — {story['title']} ({story['source']}, {story['published']})\n{story['url']}")
    missing = ([interest for interest in (interests or []) if interest not in {story["interest"] for story in stories}]
               if len(interests or []) <= 6 else [])
    if missing:
        lines.append("Sem novidade recente e verificável sobre " + ", ".join(missing) + " nesta edição.")
    lines.append("Quer que eu aprofunde alguma?")
    return "\n\n".join(lines)


def briefing_context(state):
    """Best-effort current context for an opted-in news digest; no extra alert."""
    sections = []
    active = [w["label"] for w in state.get("generic_watches", []) if w["status"] == "active"][:4]
    if active:
        sections.append("Acompanhando: " + ", ".join(active) + ".")
    try:
        import importlib.util
        path = HOME / "skills/pruce-tasks/scripts/state.py"
        spec = importlib.util.spec_from_file_location("pruce_state_for_briefing", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        current = module.run(HOME / "pruce/state.json", "active")
        tasks = current.get("tasks", []) if isinstance(current, dict) else []
        if tasks:
            sections.append("Pendências: " + "; ".join(str(t.get("title", ""))[:80] for t in tasks[:3]) + ".")
        preferred = (current.get("profile") or {}).get("preferred_ru") if isinstance(current, dict) else None
        if preferred:
            ru_path = HOME / "skills/pruce-ru/scripts/menu.py"
            ru_spec = importlib.util.spec_from_file_location("pruce_menu_for_briefing", ru_path)
            ru = importlib.util.module_from_spec(ru_spec)
            ru_spec.loader.exec_module(ru)
            menu = ru.query(ru=preferred, when="hoje", meal="almoço")
            if isinstance(menu, dict) and menu.get("status") == "ok":
                sections.append("RU hoje: " + str(menu.get("text", ""))[:500])
    except Exception as error:
        LOG.warning("briefing_context_unavailable type=%s", type(error).__name__)
    return "\n".join(sections)


def generic_results(watch, search=search_news):
    """Bounded public search; a result is a lead, never a verified offer."""
    results = search(watch["query"])
    leads = []
    for item in results[:12]:
        url = canonical_story(item.get("url") or item.get("href"))
        title = str(item.get("title") or "").strip()[:180]
        if url and len(title) >= 8:
            leads.append({"id": hashlib.sha256(url.encode()).hexdigest()[:20],
                          "title": title, "url": url, "source": str(item.get("source") or urlsplit(url).hostname)[:100]})
    return list({item["id"]: item for item in leads}.values())


def record_generic_observation(watch, outcome, result_count=None, new_count=0):
    """Persist bounded evidence about checks without storing page contents."""
    checked_at = now()
    observation = {"at": checked_at, "outcome": outcome, "new_count": new_count}
    if result_count is not None:
        observation["result_count"] = result_count
    watch["last_checked_at"] = checked_at
    watch["last_observation"] = observation
    watch["history"] = (watch.get("history", []) + [observation])[-100:]


def ensure_generic_fields(watch):
    """Keep watches created by the earlier additive schema fully usable."""
    watch.setdefault("condition", "novo resultado público que corresponda à busca")
    watch.setdefault("cadence", "twice_daily")
    watch.setdefault("last_observation", None)
    watch.setdefault("history", [])


def check_generic(watch, search=search_news):
    ensure_generic_fields(watch)
    try:
        leads = generic_results(watch, search)
    except Exception as error:
        LOG.warning("generic_search_error watch=%s type=%s", watch["id"], type(error).__name__)
        record_generic_observation(watch, "unavailable")
        return ""
    if not leads:
        record_generic_observation(watch, "ok", 0)
        return ""
    if not watch.get("baseline_ready"):
        watch["seen"] = [item["id"] for item in leads]
        watch["baseline_ready"] = True
        record_generic_observation(watch, "baseline", len(leads))
        return ""
    seen = set(watch.get("seen", []))
    fresh = [item for item in leads if item["id"] not in seen][:3]
    watch["seen"] = list(dict.fromkeys(watch.get("seen", []) + [item["id"] for item in leads]))[-500:]
    record_generic_observation(watch, "ok", len(leads), len(fresh))
    last = watch.get("last_notified_at")
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < 12 * 3600:
        return ""
    if not fresh:
        return ""
    watch["last_notified_at"] = now()
    lines = [f"👀 Novos resultados para {watch['label']} (confira os detalhes na fonte):"]
    lines += [f"• {item['title']} — {item['source']}\n{item['url']}" for item in fresh]
    return "\n".join(lines)


def tick(kind, fetch=fetch_page, search=search_news, product_search=search_products):
    with locked() as state:
        messages = []
        if kind == "price":
            for watch in state["price_watches"]:
                if watch["status"] == "active":
                    msg = check_price(watch, fetch, product_search)
                    if msg: messages.append(msg)
        elif kind in ("news", "important"):
            profile = state["news"]
            mode = (profile.get("schedule") or {}).get("mode")
            if profile["enabled"] and mode == ("important" if kind == "important" else "digest"):
                stories = collect_news(profile, search, important=kind == "important")
                if stories:
                    context = briefing_context(state) if kind == "news" else ""
                    messages.append(render_news(stories, profile["interests"]) + ("\n\n" + context if context else ""))
                    profile["delivered"] = (profile["delivered"] + [s["id"] for s in stories])[-500:]
                    profile["delivered_titles"] = (profile.get("delivered_titles", []) + [s["title"] for s in stories])[-500:]
                    profile["last_stories"] = stories
                    profile["last_digest_at"] = now()
        elif kind == "generic":
            for watch in state.get("generic_watches", []):
                if watch["status"] == "active":
                    message = check_generic(watch, search_web if search is search_news else search)
                    if message: messages.append(message)
        save_state(state)
    return "\n\n".join(messages)


def manage(data, fetch=fetch_page, search=search_news, runtime=None, product_search=search_products):
    action = data.get("action")
    with locked() as state:
        watches, profile = state["price_watches"], state["news"]
        generic = state.setdefault("generic_watches", [])
        for item in generic:
            ensure_generic_fields(item)
        if action == "add_watch":
            if data.get("opt_in") is not True:
                raise WatchError("Só ativo avisos depois do seu pedido explícito.")
            category, label, query = data.get("category"), data.get("label"), data.get("query")
            condition = data.get("condition", "novo resultado público que corresponda à busca")
            if category not in CATEGORIES or not isinstance(label, str) or not isinstance(query, str) or not 3 <= len(label.strip()) <= 100 or not 4 <= len(query.strip()) <= 180:
                raise WatchError("Diga o que acompanhar e a busca específica para encontrar novidades.")
            if not isinstance(condition, str) or not 3 <= len(condition.strip()) <= 200:
                raise WatchError("Qual condição deve gerar um aviso?")
            ident = hashlib.sha256((category + "|" + query.casefold().strip()).encode()).hexdigest()[:12]
            existing = next((w for w in generic if w["id"] == ident and w["status"] == "active"), None)
            if existing: return {"status": "exists", "watch": existing}
            # A real baseline prevents old search hits from being announced as new.
            watch = {"id": ident, "category": category, "label": label.strip(), "query": query.strip(),
                     "condition": condition.strip(), "cadence": "twice_daily",
                     "status": "active", "created_at": now(), "last_checked_at": None,
                     "last_notified_at": None, "last_observation": None, "history": [],
                     "baseline_ready": False, "seen": []}
            baseline = generic_results(watch, search_web if search is search_news else search)
            watch["seen"] = [item["id"] for item in baseline]
            watch["baseline_ready"] = bool(baseline)
            record_generic_observation(watch, "baseline" if baseline else "ok", len(baseline))
            sync_job("generic", True, "41 9,18 * * *", runtime=runtime)
            generic.append(watch)
            save_state(state)
            return {"status": "active", "id": ident, "text": f"Vou acompanhar {watch['label']} e avisar quando encontrar um resultado novo, com o link da fonte."}
        if action in ("check_watch", "cancel_watch"):
            selector = data.get("id") or data.get("label")
            matches = [w for w in generic if w["status"] == "active" and selector and (w["id"] == selector or selector.casefold() in w["label"].casefold())]
            if len(matches) != 1: raise WatchError("Qual acompanhamento? Peça a lista ou informe o nome.")
            watch = matches[0]
            if action == "cancel_watch":
                watch["status"] = "cancelled"
                if not any(w["status"] == "active" for w in generic): sync_job("generic", False, None, runtime=runtime)
                result = {"status": "cancelled", "text": f"Parei de acompanhar {watch['label']}."}
            else:
                result = {"status": "ok", "text": check_generic(watch, search_web if search is search_news else search) or "Não encontrei novidade verificável agora.", "watch": watch}
            save_state(state)
            return result
        if action == "inspect_price":
            url = clean_url(data.get("url"))
            product = extract_product(fetch(url), url)
            ident = hashlib.sha256(url.encode()).hexdigest()[:12]
            watch = next((w for w in watches if w["id"] == ident and w["status"] != "cancelled"), None)
            if watch: return {"status": "exists", "watch": watch}
            watch = {"id": ident, "url": url, "canonical_url": url, **product,
                     "initial_price": product["price"], "last_price": product["price"],
                     "lowest_seen_price": product["price"], "target_type": None, "target_price": None,
                     "target_percentage": None, "created_at": now(), "last_checked_at": now(),
                     "last_notified_at": None, "last_alerted_price": None, "status": "pending",
                     "history": [{"at": now(), "price": product["price"]}]}
            del watch["price"]
            watches.append(watch)
            save_state(state)
            LOG.info("price_watch_created watch=%s", ident)
            return {"status": "pending", "id": ident, "text": f"Encontrei {watch['name']} por {format_price(watch['last_price'], watch['currency'])}. Quer aviso em qualquer queda, abaixo de um preço, ou após uma queda percentual?"}
        if action == "discover_price":
            query = data.get("query")
            if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120 or not product_tokens(query):
                raise WatchError("Qual é o nome exato do produto que você quer acompanhar?")
            ident = hashlib.sha256(("multi:" + " ".join(product_tokens(query))).encode()).hexdigest()[:12]
            existing = next((w for w in watches if w["id"] == ident and w["status"] != "cancelled"), None)
            if existing: return {"status": "exists", "watch": existing}
            offers = discover_offers(query, fetch, product_search)
            if not offers:
                return {"status": "unavailable", "text": "Não encontrei ofertas com preço que eu consiga confirmar para esse produto. Nenhum acompanhamento foi criado."}
            cheapest = offers[0]
            watch = {"id": ident, "query": query.strip(), "offers": offers,
                     "selection_mode": None, "selected_offer_ids": [], "last_discovery_at": now(),
                     "url": cheapest["url"], "canonical_url": cheapest["url"],
                     "name": query.strip(), "merchant": cheapest["merchant"],
                     "currency": cheapest["currency"], "initial_price": cheapest["last_price"],
                     "last_price": cheapest["last_price"], "lowest_seen_price": cheapest["last_price"],
                     "target_type": None, "target_price": None, "target_percentage": None,
                     "created_at": now(), "last_checked_at": now(), "last_notified_at": None,
                     "last_alerted_price": None, "status": "pending",
                     "history": [{"at": now(), "price": cheapest["last_price"], "offer_id": cheapest["id"]}]}
            watches.append(watch)
            save_state(state)
            LOG.info("price_watch_created watch=%s offers=%d", ident, len(offers))
            lines = [f"Encontrei estes preços confirmados para {watch['name']}:"]
            lines.extend(f"{index}. {offer['merchant']} — {format_price(offer['last_price'], offer['currency'])}"
                         for index, offer in enumerate(offers, 1))
            lines.append("Quer acompanhar o menor preço entre elas, lojas específicas ou todas as ofertas? Depois me diga quando avisar.")
            return {"status": "pending", "id": ident, "offers": offers, "text": "\n".join(lines)}
        if action == "select_price":
            watch = find_watch(state, data.get("product"))
            if "offers" not in watch: raise WatchError("Esse acompanhamento usa um link único; não há lojas para selecionar.")
            mode = data.get("selection_mode")
            if mode not in ("lowest", "stores", "all"):
                raise WatchError("Quer acompanhar o menor preço, lojas específicas ou todas as ofertas?")
            selected = []
            if mode == "stores":
                stores = data.get("stores")
                if not isinstance(stores, list) or not stores or not all(isinstance(x, str) for x in stores):
                    raise WatchError("Quais lojas encontradas você quer acompanhar?")
                selected = [offer["id"] for offer in watch["offers"] if any(
                    store.casefold() in offer["merchant"].casefold() or store == offer["id"] for store in stores)]
                if not selected: raise WatchError("Não encontrei essas lojas entre as ofertas confirmadas.")
            changed = (watch.get("selection_mode"), set(watch.get("selected_offer_ids", []))) != (mode, set(selected))
            watch["selection_mode"] = mode
            watch["selected_offer_ids"] = selected
            scoped = [offer for offer in selected_offers(watch) if offer["status"] == "available"]
            if not scoped: raise WatchError("Essas lojas estão indisponíveis agora. Escolha outra oferta.")
            cheapest = min(scoped, key=lambda offer: offer["last_price"])
            if watch["status"] == "pending" or changed:
                watch["initial_price"] = cheapest["last_price"]
                watch["last_alerted_price"] = None
                watch["history"].append({"at": now(), "price": cheapest["last_price"],
                                         "offer_id": cheapest["id"], "event": "selection_changed"})
                watch["history"] = watch["history"][-100:]
            watch["last_price"] = cheapest["last_price"]
            watch["url"], watch["canonical_url"], watch["merchant"] = cheapest["url"], cheapest["url"], cheapest["merchant"]
            save_state(state)
            return {"status": watch["status"], "watch": watch,
                    "text": (f"Vou usar {len(scoped)} oferta(s), começando em {format_price(cheapest['last_price'], watch['currency'])}. "
                             + ("Quer aviso em qualquer queda, abaixo de um preço ou após uma queda percentual?" if watch["status"] == "pending" else "Atualizei as lojas acompanhadas."))}
        if action == "set_price":
            watch = find_watch(state, data.get("product"))
            if "offers" in watch and not watch.get("selection_mode"):
                raise WatchError("Quer acompanhar o menor preço, lojas específicas ou todas as ofertas?")
            typ = data.get("target_type")
            if typ not in ("any", "absolute", "percentage"): raise WatchError("Qual condição de aviso você prefere?")
            target = money(data.get("target_price")) if typ == "absolute" else None
            pct = money(data.get("target_percentage")) if typ == "percentage" else None
            if typ == "absolute" and not target or typ == "percentage" and (not pct or pct >= 100):
                raise WatchError("Informe um preço ou percentual válido.")
            # Create/update the single native job before marking this watch active.
            sync_job("price", True, "17 8,14,20 * * *", runtime=runtime)
            watch.update(target_type=typ, target_price=target, target_percentage=pct, status="active")
            save_state(state)
            return {"status": "active", "text": f"Vou acompanhar {watch['name']} e avisar quando cumprir sua condição."}
        if action == "list":
            return {"status": "ok", "price_watches": [w for w in watches if w["status"] == "active"],
                    "generic_watches": [w for w in generic if w["status"] == "active"],
                    "news": {"enabled": profile["enabled"], "interests": profile["interests"], "schedule": profile["schedule"]}}
        if action == "price_status":
            watch = find_watch(state, data.get("product"))
            suffix = f" Loja mais barata agora: {watch['merchant']}." if "offers" in watch else ""
            return {"status": "ok", "watch": watch, "text": f"Começamos em {format_price(watch['initial_price'], watch['currency'])}. Agora está em {format_price(watch['last_price'], watch['currency'])}. Menor preço que vi desde então: {format_price(watch['lowest_seen_price'], watch['currency'])}.{suffix}"}
        if action == "check_price":
            watch = find_watch(state, data.get("product"))
            check_price(watch, fetch, product_search)
            save_state(state)
            return {"status": "ok", "watch": watch}
        if action == "cancel_price":
            watch = find_watch(state, data.get("product"))
            watch["status"] = "cancelled"
            if not any(w["status"] == "active" for w in watches): sync_job("price", False, None, runtime=runtime)
            save_state(state)
            return {"status": "cancelled", "text": f"Parei de acompanhar {watch['name']}."}
        if action in ("enable_news", "update_news", "pause_news", "resume_news", "cancel_news", "send_news"):
            if action in ("enable_news", "update_news"):
                if action == "enable_news" and data.get("opt_in") is not True:
                    raise WatchError("Só ativo seu jornal depois do seu pedido explícito.")
                interests = data.get("interests", profile["interests"])
                if not isinstance(interests, list) or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 60 for x in interests):
                    raise WatchError("Quais assuntos você quer acompanhar?")
                interests = list(dict.fromkeys(x.strip() for x in interests))[:8]
                if not interests: raise WatchError("Quais assuntos você quer acompanhar?")
                spec = data.get("schedule", profile["schedule"])
                if not isinstance(spec, dict) or spec.get("mode") not in ("digest", "important"):
                    raise WatchError("Quando você quer receber o jornal?")
                zone = data.get("timezone") or profile.get("timezone")
                if not zone: raise WatchError("Qual é seu fuso horário?")
                ZoneInfo(zone)
                if spec["mode"] == "digest":
                    days = spec.get("days", "daily")
                    if days != "daily" and (not isinstance(days, list) or not all(type(x) is int and 0 <= x <= 6 for x in days)):
                        raise WatchError("Quais dias você quer receber o jornal?")
                    at = spec.get("time")
                    if not isinstance(at, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
                        raise WatchError("Que horas você quer receber o jornal?")
                    expr = schedule(at, days, zone, runtime)
                else: expr = important_schedule(zone, runtime)
                kind = "important" if spec["mode"] == "important" else "news"
                sync_job(kind, True, expr, runtime=runtime)
                sync_job("news" if kind == "important" else "important", False, None, runtime=runtime)
                profile.update(enabled=True, interests=interests, schedule=spec, timezone=zone)
            elif action == "pause_news":
                profile["enabled"] = False
                sync_job("news", False, None, runtime=runtime)
                sync_job("important", False, None, runtime=runtime)
            elif action == "resume_news":
                if not profile["schedule"]: raise WatchError("Configure o jornal antes de retomá-lo.")
                spec = profile["schedule"]
                kind = "important" if spec["mode"] == "important" else "news"
                expr = important_schedule(profile["timezone"], runtime) if kind == "important" else schedule(spec["time"], spec.get("days", "daily"), profile["timezone"], runtime)
                sync_job(kind, True, expr, runtime=runtime)
                profile["enabled"] = True
            elif action == "cancel_news":
                sync_job("news", False, None, runtime=runtime)
                sync_job("important", False, None, runtime=runtime)
                profile.update(enabled=False, interests=[], schedule=None, delivered=[], delivered_titles=[], last_stories=[])
            elif action == "send_news":
                if not profile["enabled"]: raise WatchError("Seu jornal ainda não está ativo.")
                stories = collect_news(profile, search)
                if stories:
                    profile["delivered"] = (profile["delivered"] + [s["id"] for s in stories])[-500:]
                    profile["delivered_titles"] = (profile.get("delivered_titles", []) + [s["title"] for s in stories])[-500:]
                    profile["last_stories"] = stories
                    profile["last_digest_at"] = now()
                save_state(state)
                return {"status": "ok", "text": render_news(stories, profile["interests"]) or "Não encontrei notícias novas e verificáveis para seu jornal agora."}
            save_state(state)
            return {"status": "ok", "news": profile}
        if action == "story":
            index = data.get("index")
            if type(index) is not int or not 1 <= index <= len(profile["last_stories"]): raise WatchError("Qual notícia do último jornal?")
            return {"status": "ok", "story": profile["last_stories"][index - 1]}
    raise WatchError("Não entendi o acompanhamento pedido.")


def main():
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "tick":
            result = tick(sys.argv[2])
            if result: print(result)
        else:
            result = manage(json.load(sys.stdin))
            print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        if len(sys.argv) >= 2 and sys.argv[1] == "tick":
            LOG.warning("watch_tick_error type=%s", type(error).__name__)
        else:
            print(json.dumps({"status": "error", "text": str(error) if isinstance(error, WatchError) else "Não consegui concluir este acompanhamento agora."}, ensure_ascii=False))


if __name__ == "__main__": main()
