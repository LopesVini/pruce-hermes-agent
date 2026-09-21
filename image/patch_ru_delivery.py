"""Pinned-image presentation patch; native cron storage/execution stays unchanged."""
import hashlib
from pathlib import Path

PATH = Path('/opt/hermes/cron/scheduler_delivery.py')
UPSTREAM_SHA256 = '43ea115bba07e6b789a1c8552dd606bd23e43ae6b80332844520e6510f44d96d'
ANCHOR = '    if wrap_response:\n        task_name = job.get("name", job["id"])\n'
REPLACEMENT = ('    if wrap_response and not (not for_failure and _pruce_plain_delivery_job(job)):\n'
               '        task_name = job.get("name", job["id"])\n')
HELPER = '''
def _pruce_plain_delivery_job(job: dict) -> bool:
    """Only authenticated Prucê script jobs get a clean delivery body."""
    import json
    import re
    if job.get("no_agent") is not True:
        return False
    try:
        cfg = json.loads(job.get("prompt", ""))
        if cfg.get("opt_in") is not True:
            return False
        for name, script, kind in (
            ("pruce-price-watch", "pruce-price-watch.py", "pruce_price_v1"),
            ("pruce-news-digest", "pruce-news-digest.py", "pruce_news_v1"),
            ("pruce-news-important", "pruce-news-important.py", "pruce_news_important_v1"),
        ):
            if (job.get("name"), job.get("script"), cfg.get("kind")) == (name, script, kind):
                return True
        if cfg.get("kind") == "pruce_ru_daily_v1":
            return job.get("name") == "pruce-ru-daily" and job.get("script") == "pruce-ru-daily.py"
        key = cfg.get("key", "")
        return (cfg.get("kind") == "pruce_ru_once_v1"
                and isinstance(key, str) and bool(re.fullmatch(r"[a-f0-9]{12}", key))
                and job.get("name") == f"pruce-ru-once:{key}"
                and job.get("script") == f"pruce-ru-once-{key}.py")
    except (ValueError, TypeError, AttributeError):
        return False

'''


def patch_source(source):
    if hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256:
        raise RuntimeError('unexpected Hermes delivery source; review patch before changing base')
    text = source.decode()
    if text.count(ANCHOR) != 1 or text.count('def _deliver_result(') != 1:
        raise RuntimeError('unexpected Hermes delivery formatting contract')
    return text.replace('def _deliver_result(', HELPER + 'def _deliver_result(', 1).replace(
        ANCHOR, REPLACEMENT, 1).encode()


if __name__ == '__main__':
    PATH.write_bytes(patch_source(PATH.read_bytes()))
