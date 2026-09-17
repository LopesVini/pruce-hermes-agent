"""Public Fump menu, one bounded HTTP GET; no credentials or local runtime services."""
import argparse
from datetime import date, datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import sys
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE = "https://fump.ufmg.br/cardapio-do-dia/"
ENDPOINT = "https://fump.ufmg.br:3003/cardapios/cardapio"
# Official API groups Campus Saúde and Direito into one menu (id=2).
RESTAURANTS = {
    "setorial_1": (6, "RU I"), "setorial_2": (1, "RU II"),
    "saude": (2, "RU Saúde"), "direito": (2, "RU Direito"), "ica": (5, "RU ICA"),
}
ALIASES = {
    "ru i": "setorial_1", "ru 1": "setorial_1", "setorial i": "setorial_1",
    "setorial 1": "setorial_1", "ru setorial i": "setorial_1",
    "ru ii": "setorial_2", "ru 2": "setorial_2", "setorial ii": "setorial_2",
    "setorial 2": "setorial_2", "ru setorial ii": "setorial_2",
    "saude": "saude", "ru saude": "saude", "campus saude": "saude",
    "direito": "direito", "ru direito": "direito",
    "ica": "ica", "ru ica": "ica", "montes claros": "ica",
    "campus montes claros": "ica",
}
MEALS = {"almoco": "Almoço", "jantar": "Jantar"}
FIELDS = {"todos", "sobremesa", "vegetariano", "principal", "acompanhamentos", "entrada"}
DEFAULT_STATE = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes")) / "pruce/state.json"


def normalize(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", value.lower())
                            if unicodedata.category(c) != "Mn").split())


def resolve_ru(value):
    key = normalize(value)
    if key in RESTAURANTS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    raise ValueError("Qual RU você usa: I, II, Saúde, Direito ou ICA?")


def resolve_date(value, now=None):
    today = (now or datetime.now(ZoneInfo("America/Sao_Paulo"))).astimezone(
        ZoneInfo("America/Sao_Paulo")).date()
    relative = normalize(value)
    if relative in {"hoje", "amanha"}:
        return today + timedelta(days=relative == "amanha")
    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError as error:
            raise ValueError("Qual data? Pode dizer hoje, amanhã ou DD/MM/AAAA.") from error


def preferred_ru(path):
    # Reuse canonical validation, including corruption handling; read creates nothing.
    script = Path(__file__).resolve().parents[2] / "pruce-tasks/scripts/state.py"
    spec = importlib.util.spec_from_file_location("pruce_ru_state", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run(path, "read")["profile"].get("preferred_ru")


def fetch_menu(restaurant_id, day):
    query = urlencode({"id": restaurant_id, "dataInicio": day.isoformat(),
                       "dataFim": day.isoformat()})
    request = Request(ENDPOINT + "?" + query, headers={
        "Accept": "application/json", "User-Agent": "Pruce-RU/1.0"})
    with urlopen(request, timeout=6) as response:
        raw = response.read(512_001)
    if len(raw) > 512_000:
        raise ValueError("oversize source response")
    return json.loads(raw)


def extract_menu(payload, restaurant_id, day, meal):
    # Unexpected schema/date/id is a source failure, never a different day's menu.
    if not isinstance(payload, dict) or payload.get("id") != restaurant_id:
        raise ValueError("source restaurant mismatch")
    menus = payload["cardapios"]
    if not isinstance(menus, list):
        raise ValueError("invalid menus")
    items = []
    for menu in menus:
        if date.fromisoformat(menu["data"].split("T")[0]) != day:
            raise ValueError("source date mismatch")
        if not isinstance(menu["refeicoes"], list):
            raise ValueError("invalid meals")
        for entry in menu["refeicoes"]:
            if entry["tipoRefeicao"] != meal:
                continue
            if not isinstance(entry["pratos"], list):
                raise ValueError("invalid dishes")
            for dish in entry["pratos"]:
                label, description = dish["tipoPrato"], dish["descricaoPrato"]
                if not all(isinstance(v, str) and v.strip() and len(v) < 1000
                           for v in (label, description)):
                    raise ValueError("invalid dish")
                items.append({"tipo": label.strip(), "descricao": description.strip()})
    return items


def select_items(items, field):
    prefixes = {"sobremesa": "sobremesa", "principal": "prato proteico 1",
                "vegetariano": "prato proteico 3", "acompanhamentos": "acompanhamento",
                "entrada": "entrada"}
    if field == "todos":
        return items
    return [item for item in items if normalize(item["tipo"]).startswith(prefixes[field])]


def query(ru=None, when="hoje", meal="almoço", field="todos", state_path=DEFAULT_STATE,
          now=None, fetch=fetch_menu):
    try:
        ru = resolve_ru(ru) if ru else preferred_ru(state_path)
        if not ru:
            return {"status": "ru_required", "text": "Qual RU você usa: I, II, Saúde, Direito ou ICA?"}
        day = resolve_date(when, now)
        meal = MEALS[normalize(meal)]
        field = normalize(field)
        if field not in FIELDS:
            raise ValueError("Qual parte do cardápio você quer consultar?")
    except (ValueError, KeyError, OSError):
        return {"status": "invalid_request", "text": "Não consegui identificar RU/data ou ler sua preferência. Informe o RU e a data."}
    restaurant_id, name = RESTAURANTS[ru]
    base = {"ru": ru, "date": day.isoformat(), "meal": meal, "source": SOURCE}
    try:
        payload = fetch(restaurant_id, day)
        items = extract_menu(payload, restaurant_id, day, meal)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {**base, "status": "source_unavailable",
                "text": "Não consegui consultar a Fump agora. O cardápio está indisponível."}
    heading = f"🍽️ {name} — {meal.lower()} de {day.strftime('%d/%m/%Y')}"
    if ru in {"saude", "direito"}:
        heading += " (cardápio conjunto Saúde/Direito)"
    if not items:
        return {**base, "status": "not_published",
                "text": heading + "\nA Fump não publicou cardápio para essa refeição/data."}
    selected = select_items(items, field)
    lines = [f"{item['tipo']}: {item['descricao']}" for item in selected]
    if not selected:
        lines = ["Esse item não está informado no cardápio publicado."]
    if field == "vegetariano":
        lines.append("A fonte não informa ingredientes nem certifica que o prato é vegetariano.")
    return {**base, "status": "ok", "items": selected,
            "text": heading + "\n" + "\n".join(lines)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ru")
    parser.add_argument("--date", default="hoje")
    parser.add_argument("--meal", default="almoço", choices=("almoço", "almoco", "jantar"))
    parser.add_argument("--field", default="todos", choices=sorted(FIELDS))
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    print(json.dumps(query(args.ru, args.date, args.meal, args.field, args.state),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
