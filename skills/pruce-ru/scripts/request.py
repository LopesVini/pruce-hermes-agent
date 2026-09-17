"""RU entry point: select intent before any menu fetch or scheduling action."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subscription as sub


def intent(text):
    value = sub.menu.normalize(text)
    if re.search(r"(?:^(?:para|pare)\b|\b(?:cancela|cancele|nao quero mais|nao me mand)).*\b(?:cardapio|bandejao|ru)\b", value):
        return "cancel"
    delivery = bool(re.search(r"\bme (?:manda|mande|envia|envie|avisa|avise)\b", value))
    recurring = bool(re.search(r"\btod[oa]s? (?:os? )?dias?\b|\bdiari[oa]\b|segunda.*sexta", value))
    if delivery and recurring:
        return "recurring"
    if delivery and (read_time(value) or "daqui" in value or "antes do almoco" in value):
        return "once"
    if re.search(r"\b(?:troca|troque|muda|mude|altera|altere)\b", value):
        return "change"
    return "query"


def read_time(text):
    value = sub.menu.normalize(text)
    found = re.search(r"\bas\s+(\d{1,2})(?:h(\d{2})?|:(\d{2}))?\b", value)
    if not found:
        found = re.search(r"\b(\d{1,2})(?:h(\d{2})?|:(\d{2}))\b", value)
    if not found:
        found = re.fullmatch(r"\s*(\d{1,2})\s*", value)
    if not found:
        return None
    groups = found.groups()
    minute = next((value for value in groups[1:] if value is not None), "00")
    return f"{int(groups[0]):02d}:{minute}"


def read_ru(text):
    value = sub.menu.normalize(text)
    for alias in sorted(sub.menu.ALIASES, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", value):
            return sub.menu.ALIASES[alias]
    return None


def read_date(text):
    value = sub.menu.normalize(text)
    explicit = re.search(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b", value)
    return explicit.group() if explicit else "amanhã" if "amanha" in value else "hoje"


def lunch_minus_hour(at):
    if not at or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
        raise sub.RequestError("Você costuma almoçar que horas?")
    hour, minute = map(int, at.split(":"))
    if hour == 0:
        raise sub.RequestError("Esse envio ficaria no dia anterior. Que horário de envio você prefere?")
    return f"{hour - 1:02d}:{minute:02d}"


def flow_value(profile, **updates):
    value = {"stage": "awaiting_lunch_time", "pending_lunch_time": None,
             "usual_lunch_time": None, "ru": profile.get("preferred_ru")}
    value.update(profile.get("ru_delivery", {}))
    value.update(updates)
    return value


def save_flow(path, value):
    sub.state.run(path, "profile", {"profile": {"ru_delivery": value}})


def handle(data, home=None, runtime=None, fetch=None):
    home = home or sub.home_path()
    text = data["text"]
    route = intent(text)
    value = sub.menu.normalize(text)
    path = home / "pruce/state.json"
    profile = sub.state.run(path, "read")["profile"]
    flow = profile.get("ru_delivery")
    ru = read_ru(text) or data.get("ru")
    base = {key: data[key] for key in ("timezone", "deliver") if key in data}
    def manage(**payload):
        return sub.manage({**base, **payload}, home=home, runtime=runtime)

    if route == "cancel":
        result = manage(action="cancel")
        save_flow(path, flow_value(profile, stage="cancelled", pending_lunch_time=None))
        return {**result, "intent": route}
    if route in {"once", "recurring", "change"}:
        payload = {"action": "send_once" if route == "once" else "subscribe", "opt_in": True}
        if not ru and route == "once" and flow:
            ru = profile.get("preferred_ru") or flow["ru"]
        if ru:
            payload["ru"] = ru
        at = read_time(text)
        if at:
            payload["time"] = at
        if route == "once":
            delay = re.search(r"daqui (?:a )?(\d+|uma?|cinco) (minutos?|horas?)", value)
            if delay:
                number = int(delay[1]) if delay[1].isdigit() else 5 if delay[1] == "cinco" else 1
                payload["delay_minutes"] = number * (60 if delay[2].startswith("hora") else 1)
            elif "daqui" in value:
                raise sub.RequestError("Daqui a quanto tempo você quer receber o cardápio?")
            payload["date"] = read_date(text)
        else:
            if "segunda" in value and "sexta" in value:
                payload["days"] = "weekdays"
            elif re.search(r"tod[oa]s? (?:os? )?dias?\b|diari[oa]", value):
                payload["days"] = "daily"
            if route == "change" and not at and not ru:
                raise sub.RequestError("Você quer mudar o RU ou o horário de envio?")
        result = manage(**payload)
        if route != "once":
            save_flow(path, flow_value(profile, stage="accepted", pending_lunch_time=None,
                                      ru=ru or profile.get("preferred_ru")))
        return {**result, "intent": route}

    # Follow-ups are bound to the persisted offer, not a free-floating "sim".
    refusal = bool(re.match(r"^(?:nao\b|agora nao\b|nao quero\b)", value))
    acceptance = bool(re.fullmatch(r"(?:sim|quero|pode|pode ser|pode mandar|aceito)(?:[, ]+(?:mas )?(?:todo dia|todos os dias|de segunda a sexta))?[.! ]*", value))
    if flow and flow["stage"] in {"awaiting_lunch_time", "awaiting_consent"} and refusal:
        save_flow(path, flow_value(profile, stage="declined", pending_lunch_time=None))
        return {"intent": "decline", "status": "declined", "text": "Tudo bem. Não vou ativar o envio diário."}
    if flow and flow["stage"] == "awaiting_consent" and acceptance:
        at = lunch_minus_hour(flow["pending_lunch_time"])
        days = "daily" if re.search(r"todo dia|todos os dias", value) else "weekdays"
        result = manage(action="subscribe", opt_in=True,
                        ru=profile.get("preferred_ru") or flow["ru"], time=at, days=days)
        save_flow(path, flow_value(profile, stage="accepted", pending_lunch_time=None,
                                  usual_lunch_time=flow["pending_lunch_time"]))
        return {**result, "intent": "accept"}
    at = read_time(text)
    if flow and at and not ru and (flow["stage"] in {"awaiting_lunch_time", "awaiting_consent"}
                                  or (flow["stage"] == "accepted" and re.search(r"almoco|almocar", value))):
        sending = lunch_minus_hour(at)
        save_flow(path, flow_value(profile, stage="awaiting_consent", pending_lunch_time=at))
        label = sub.menu.RESTAURANTS[profile.get("preferred_ru") or flow["ru"]][1]
        return {"intent": "lunch_time", "status": "awaiting_consent",
                "text": f"Quer que eu te mande o cardápio do {label} 1h antes do almoço, de segunda a sexta, às {sending}? Posso usar outros dias se você preferir."}
    if acceptance or refusal:
        return {"intent": "clarify", "status": "clarification", "text": "Você quer consultar o cardápio ou configurar um envio?"}

    field = data.get("field", "sobremesa" if "sobremesa" in value else "vegetariano" if "vegetarian" in value else "todos")
    kwargs = {"ru": ru, "when": read_date(text), "meal": "jantar" if "jantar" in value else "almoço",
              "field": field, "state_path": path}
    if fetch:
        kwargs["fetch"] = fetch
    result = sub.menu.query(**kwargs)
    if result["status"] == "ok" and not flow:
        status = manage(action="status")
        if status["status"] == "inactive":
            save_flow(path, flow_value(profile, ru=result["ru"]))
            result["text"] += "\n\nVocê costuma almoçar que horas?"
        else:
            save_flow(path, flow_value(profile, stage="accepted"))
    return {**result, "intent": "query"}


def main():
    try:
        result = handle(json.load(sys.stdin))
    except Exception as error:
        result = {"status": "error", "text": str(error) if isinstance(error, sub.RequestError)
                  else "Não consegui concluir o pedido. Nenhum envio foi confirmado."}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
