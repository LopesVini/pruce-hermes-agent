"""Small adapter to Hermes' native cron store/provider; no scheduler of its own."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

NAME = "pruce-ru-daily"
SCRIPT = "pruce-ru-daily.py"
MARKER = "pruce_ru_daily_v1"
ONCE_MARKER = "pruce_ru_once_v1"
HERE = Path(__file__).resolve().parent


class RequestError(ValueError):
    """Safe clarification authored by this adapter, not a runtime diagnostic."""


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


menu = load_script("subscription_menu", HERE / "menu.py")
state = load_script("subscription_state", HERE.parents[1] / "pruce-tasks/scripts/state.py")


def home_path():
    return Path(os.environ.get("HERMES_HOME", "/var/lib/hermes"))


def native_runtime():
    sys.path.insert(0, "/opt/hermes")
    from cron import jobs, scheduler
    import hermes_time
    return jobs, scheduler, hermes_time


def current_origin():
    from tools.cronjob_job_args import _origin_from_env
    from gateway.session_context import get_session_env
    kind = get_session_env("HERMES_SESSION_CHAT_TYPE", "")
    if kind and kind not in {"dm", "private", "direct"}:
        raise RequestError("O envio diário só pode ser configurado na sua conversa privada.")
    return _origin_from_env()


def configuration(job):
    try:
        value = json.loads(job.get("prompt", ""))
        if value.get("kind") == MARKER and job.get("name") == NAME and job.get("script") == SCRIPT:
            return value
        key = value.get("key", "")
        if (value.get("kind") == ONCE_MARKER and re.fullmatch(r"[a-f0-9]{12}", key)
                and job.get("name") == f"pruce-ru-once:{key}"
                and job.get("script") == f"pruce-ru-once-{key}.py"):
            return value
        return None
    except (ValueError, AttributeError, TypeError):
        return None


def schedule_expression(at, days, user_zone, scheduler_zone, now=None):
    if not isinstance(at, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
        raise RequestError("Qual horário? Por exemplo, 11h.")
    if days not in {"daily", "weekdays"}:
        raise RequestError("Todos os dias ou de segunda a sexta?")
    user_zone = ZoneInfo(user_zone)
    current = (now or datetime.now(timezone.utc)).astimezone(user_zone)
    hour, minute = map(int, at.split(":"))
    # Hermes cron has a profile timezone, not a per-job timezone. Translate only
    # when the relative offset is stable; never silently flatten DST changes.
    signatures = set()
    for index in range(400):
        day = current.date() + timedelta(days=index)
        local = datetime.combine(day, datetime.min.time(), user_zone).replace(hour=hour, minute=minute)
        scheduled = local.astimezone(scheduler_zone)
        signatures.add((scheduled.hour, scheduled.minute, (scheduled.date() - day).days))
    if len(signatures) != 1:
        raise RequestError("Não consegui garantir o horário nesse fuso. O envio não foi ativado; o fuso da instalação precisa ser ajustado primeiro.")
    converted_hour, converted_minute, shift = signatures.pop()
    weekdays = "*" if days == "daily" else ",".join(str((day + shift) % 7) for day in range(1, 6))
    return f"{converted_minute} {converted_hour} * * {weekdays}"


def install_runner(home, once_key=None):
    directory = home / "scripts"
    directory.mkdir(parents=True, exist_ok=True)
    # Use installed variant code after every image upgrade; no machine paths,
    # copied menu snapshot, credentials or interpolated owner text.
    content = ("from pathlib import Path\nimport os, runpy, sys\n"
               "home = Path(os.environ.get('HERMES_HOME', '/var/lib/hermes'))\n"
               + (f"sys.argv = ['daily.py', '--once-key', '{once_key}']\n" if once_key else "")
               + "runpy.run_path(str(home / 'skills/pruce-ru/scripts/daily.py'), run_name='__main__')\n")
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as output:
        temporary = Path(output.name)
        output.write(content)
    temporary.chmod(0o644)
    os.replace(temporary, directory / (f"pruce-ru-once-{once_key}.py" if once_key else SCRIPT))


@contextmanager
def subscription_lock(home):
    directory = home / "pruce"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "ru-subscription.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def manage(data, home=None, runtime=None):
    home = home or home_path()
    state_path = home / "pruce/state.json"
    action = data.get("action")
    if action not in {"subscribe", "send_once", "cancel", "status"}:
        raise RequestError("Não consegui identificar o pedido de envio ou cancelamento.")
    if action in {"subscribe", "send_once"} and data.get("opt_in") is not True:
        raise RequestError("Só agendo o cardápio após um pedido explícito seu.")
    jobs, scheduler, clock = runtime or native_runtime()
    with subscription_lock(home):
        all_managed = [job for job in jobs.list_jobs(include_disabled=True) if configuration(job)]
        managed = [job for job in all_managed if configuration(job)["kind"] == MARKER]
        if action == "status":
            return {"status": "active" if any(job.get("enabled", True) for job in managed) else "inactive",
                    "subscriptions": [{"id": job["id"], **configuration(job)} for job in managed]}
        if action == "cancel":
            for job in all_managed:
                if not jobs.remove_job(job["id"]):
                    raise RequestError("Não consegui cancelar o envio. Tente novamente.")
            scheduler._notify_provider_jobs_changed()
            return {"status": "cancelled", "text": "Cancelei os envios de cardápio."}
        profile = state.run(state_path, "read")["profile"]
        previous = configuration(managed[0]) if managed else {}
        ru = menu.resolve_ru(data["ru"]) if data.get("ru") else profile.get("preferred_ru") or previous.get("ru")
        if not ru:
            raise RequestError("Qual RU você usa: I, II, Saúde, Direito ou ICA?")
        at = data.get("time") or previous.get("time")
        days = data.get("days") or previous.get("days")
        known_zone = profile["timezone"]
        user_zone = data.get("timezone") or (known_zone["value"] if known_zone["status"] == "known" else None) or previous.get("timezone")
        if not user_zone:
            raise RequestError("Qual é seu fuso? Você está no horário de Brasília?")
        origin = current_origin()
        destination = None
        if origin:
            destination = f"{origin['platform']}:{origin['chat_id']}"
            if origin.get("thread_id"):
                destination += ":" + str(origin["thread_id"])
        # A new one-off belongs to the requesting chat, even when a recurring
        # subscription already delivers to another channel. Recurring changes
        # keep the established subscription destination.
        deliver = data.get("deliver") or (destination if action == "send_once" else
                   (managed[0].get("deliver") if managed else None) or destination)
        # Hermes' local terminal bridges fresh session vars on every command.
        # Capture that trusted context; never use home/broadcast fallbacks.
        if not isinstance(deliver, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*:[^\s,:]+(?::[^\s,:]+)?", deliver) or deliver.split(":")[0] in {"bot-chat", "all", "local", "origin"}:
            raise RequestError("Não consegui identificar este chat para o envio. Nenhuma notificação foi ativada.")
        scheduler_zone = clock.now().tzinfo
        if not isinstance(scheduler_zone, ZoneInfo) and scheduler_zone.utcoffset(None) != timedelta(0):
            raise RequestError("O fuso desta instalação precisa ser ajustado antes de ativar o envio.")
        once_key = None
        if action == "send_once":
            now = clock.now().astimezone(ZoneInfo(user_zone))
            if "delay_minutes" in data:
                delay = data["delay_minutes"]
                if type(delay) is not int or not 1 <= delay <= 10080:
                    raise RequestError("Daqui a quantos minutos você quer receber?")
                send_at = now + timedelta(minutes=delay)
            else:
                if not isinstance(data.get("time"), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", data["time"]):
                    raise RequestError("Que horas você quer receber o cardápio?")
                raw_day = data.get("date", "hoje")
                relative = menu.normalize(raw_day)
                day = (now.date() + timedelta(days=relative == "amanha") if relative in {"hoje", "amanha"}
                       else menu.resolve_date(raw_day, now))
                hour, minute = map(int, data["time"].split(":"))
                send_at = datetime.combine(day, datetime.min.time(), ZoneInfo(user_zone)).replace(hour=hour, minute=minute)
            if send_at <= now:
                raise RequestError("Esse horário já passou. Para qual dia e horário você quer o envio?")
            expr = send_at.isoformat()
            once_key = hashlib.sha256((send_at.astimezone(timezone.utc).isoformat() + "|" + deliver).encode()).hexdigest()[:12]
            managed = [job for job in all_managed if configuration(job).get("key") == once_key]
            config = {"kind": ONCE_MARKER, "key": once_key, "ru": ru,
                      "send_at": expr, "timezone": user_zone, "opt_in": True}
        else:
            expr = schedule_expression(at, days, user_zone, scheduler_zone)
            config = {"kind": MARKER, "ru": ru, "time": at, "days": days,
                      "timezone": user_zone, "opt_in": True}
        payload = {"prompt": json.dumps(config, ensure_ascii=False), "script": f"pruce-ru-once-{once_key}.py" if once_key else SCRIPT,
                   "no_agent": True, "deliver": deliver, "failure_deliver": "local",
                   "repeat": 1 if once_key else None, "name": f"pruce-ru-once:{once_key}" if once_key else NAME}
        install_runner(home, once_key)
        if managed:
            result = jobs.update_job(managed[0]["id"], {**payload, "schedule": jobs.parse_schedule(expr)})
            if result is None:
                raise RequestError("Não consegui atualizar o envio. Tente novamente.")
            if not result.get("enabled", True):
                result = jobs.resume_job(result["id"])
                if result is None:
                    raise RequestError("Não consegui reativar o envio. Tente novamente.")
            # Unlike best-effort change notifications, registration errors must
            # prevent a success claim for an external/cloud scheduler provider.
            from cron.scheduler_provider import resolve_cron_scheduler
            resolve_cron_scheduler().register_job(result)
        else:
            result = scheduler.create_job_with_scheduler_registration(**payload, schedule=expr, origin=origin)
        # Consolidate only jobs bearing our exact name/script/marker.
        for duplicate in managed[1:]:
            if not jobs.remove_job(duplicate["id"]):
                raise RequestError("Não consegui remover um envio duplicado. Confira antes de tentar novamente.")
        scheduler._notify_provider_jobs_changed()
        state.run(state_path, "profile", {"profile": {"preferred_ru": ru}})
        if once_key:
            return {"status": "scheduled", "intent": "once", "job_id": result["id"], "schedule": expr,
                    "text": f"Agendei o cardápio do {menu.RESTAURANTS[ru][1]} para {send_at.strftime('%d/%m às %H:%M')} ({user_zone})."}
        label = "todos os dias" if days == "daily" else "de segunda a sexta"
        return {"status": "scheduled", "job_id": result["id"], "schedule": expr,
                "text": f"Vou enviar o cardápio do {menu.RESTAURANTS[ru][1]} {label}, às {at} ({user_zone}). Se não houver cardápio disponível, não envio."}


def main():
    try:
        data = json.load(sys.stdin)
        result = manage(data)
    except Exception as error:
        # Details of cron registration may include configuration: keep them
        # out of user-facing replies; preserve the job for status/retry.
        result = {"status": "error", "text": str(error) if isinstance(error, RequestError)
                  else "Não consegui concluir o agendamento. Confira o envio antes de tentar novamente."}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
