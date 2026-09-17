"""Real /init + Hermes transport, private fixture, empty nocopy volumes.

PRUCE_TEST_IMAGE=<image> python3 -B tests/check_cloud_bootstrap.py
Optional PRUCE_BASELINE_IMAGE reproduces the old permanent-park failure first.
No real Plow API, credentials, model, owner volume or messaging service is used.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

IMAGE = os.environ.get("PRUCE_TEST_IMAGE", "pruce-oneclick-home-chat:check")
PREFIX = "pruce-boot-fixture-" + uuid.uuid4().hex[:10]
FIXTURE = Path(__file__).resolve().parent / "fixtures/plow_bootstrap_api.py"


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          check=check, timeout=45).stdout.strip()


def python(container, code):
    return docker("exec", container, "/opt/hermes/.venv/bin/python3", "-c", code)


def status(api):
    return json.loads(python(api, "import json,urllib.request;print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/fixture/status'))))"))


def create_chat(api, first_message=False):
    python(api, "import urllib.request,json;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080/fixture/create',data=json.dumps({'first_message':" + repr(first_message) + "}).encode(),headers={'Content-Type':'application/json'})).read()")


def until(predicate, seconds=65):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.5)
    raise AssertionError("isolated bootstrap condition did not become true")


def parked(agent):
    return python(agent, "from pathlib import Path;p=Path('/run/plow-init.parked');print(p.read_text() if p.exists() else '')")


def configured(agent):
    return python(agent, "from pathlib import Path;print((Path('/run/s6/container_environment')/'PLOW_HOME_CHANNEL').exists())") == "True"


def scenario(image, name, baseline=False, existing=False):
    network = PREFIX + "-" + name
    api, agent, volume = network + "-api", network + "-agent", network + "-home"
    try:
        docker("network", "create", "--internal", network)
        docker("volume", "create", volume)
        docker("run", "-d", "--platform", "linux/amd64", "--name", api, "--network", network,
               "--mount", f"type=bind,src={FIXTURE},dst=/fixture.py,readonly",
               "--entrypoint", "/opt/hermes/.venv/bin/python3", image, "/fixture.py")
        time.sleep(1)
        if existing:
            create_chat(api)
        docker("run", "-d", "--platform", "linux/amd64", "--name", agent, "--network", network,
               "--mount", f"type=volume,src={volume},dst=/var/lib/hermes,volume-nocopy",
               "--env", "PLOW_API_BASE=http://" + api + ":8080", image)
        until(lambda: status(api)["calls"] > 0, seconds=20)
        if baseline:
            until(lambda: bool(parked(agent)), seconds=20)
            reason = parked(agent)
            assert "cannot tell which chat is home" in reason, reason
            before = status(api)["calls"]
            create_chat(api, first_message=True)
            time.sleep(5)
            assert status(api)["calls"] == before and parked(agent) == reason
            print("BASELINE: 0 chats -> permanently parked; later chat did not trigger another identity GET")
            return
        if not existing:
            assert not parked(agent)
            assert not configured(agent)
            # Several seconds after boot; leave the native 30-second poll untouched.
            time.sleep(5)
            create_chat(api, first_message=True)
            appeared = time.monotonic()
            until(lambda: configured(agent))
            print(f"NEW: 0 chats -> owner chat detected without restart in {time.monotonic() - appeared:.1f}s")
            until(lambda: bool(status(api)["replies"]), seconds=40)
            reply = status(api)["replies"][0].get("body", "")
            assert reply and ("status" in reply.lower() or "session" in reply.lower()), "first /status response not observed"
            until(lambda: python(agent, "from pathlib import Path;p=Path('/var/lib/hermes/plow_chat_last_uid');print(p.read_text() if p.exists() else '')") == "msg_first", seconds=20)
            print("FIRST MESSAGE: real Hermes /status answered through native Plow REST delivery; checkpoint=msg_first")
        else:
            until(lambda: configured(agent), seconds=25)
            until(lambda: status(api)["sockets"] > 0, seconds=25)
            print("EXISTING CHAT: empty volume boots and native Plow socket connects")
        facts = json.loads(python(agent, "from pathlib import Path;import json;env=Path('/run/s6/container_environment');home=Path('/var/lib/hermes');print(json.dumps({'id':(env/'AGENT_ID').read_text().strip(),'proxy':(env/'PLOW_AGENT_TOKEN').read_text().strip()=='proxied','mac':(env/'PLOW_MCP_URL').exists(),'credentials':Path('/var/lib/plow/credentials').exists(),'persona':(home/'SOUL.md').exists(),'ru':(home/'skills/pruce-ru/SKILL.md').exists()}))"))
        assert facts == {"id": "pruce", "proxy": True, "mac": False, "credentials": False, "persona": True, "ru": True}, facts
        assert not parked(agent)
        if not existing:
            # Valid canonical state and disposable ledgers, never a developer's home.
            python(agent, "import subprocess,json;from pathlib import Path;subprocess.run(['/opt/hermes/.venv/bin/python3','/opt/hermes/skills/pruce-tasks/scripts/state.py','profile'],input=json.dumps({'profile':{'preferred_ru':'setorial_2'}}),text=True,check=True,stdout=subprocess.DEVNULL);p=Path('/var/lib/hermes/pruce');(p/'sources.json').write_text('{\"fixture\":\"source\"}');(p/'operations.json').write_text('{\"fixture\":\"operation\"}')")
            capture = "from pathlib import Path;import hashlib,json;p=Path('/var/lib/hermes');names=['pruce/state.json','pruce/sources.json','pruce/operations.json','plow_chat_last_uid'];print(json.dumps({n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in names}))"
            before = python(agent, capture)
            headline = reply.splitlines()[0]
            count_status = lambda: sum(r.get("body", "").splitlines()[0:1] == [headline] for r in status(api)["replies"])
            replies, sockets = count_status(), status(api)["sockets"]
            restore_count = lambda: int(python(agent, "from pathlib import Path;p=Path('/var/lib/hermes/logs/gateway.log');print(p.read_text(errors='replace').count('queued during startup restore'))"))
            restored = restore_count()
            docker("restart", "--time", "35", agent)
            until(lambda: configured(agent), seconds=25)
            until(lambda: status(api)["sockets"] > sockets, seconds=25)
            until(lambda: restore_count() > restored, seconds=40)
            time.sleep(1)
            assert python(agent, capture) == before
            # A fixture without inference can produce setup-wake diagnostics;
            # compare the actual command response, not all unrelated outbound text.
            assert count_status() == replies == 1, "first /status message replayed after restart"
            print("RESTART: canonical state, source/operation fixtures and checkpoint unchanged; first message not replayed")
        print("ENVIRONMENT: PLOW_API_BASE only, AGENT_ID=pruce, no Mac/local credential file; persona and RU seeded")
    finally:
        for container in (agent, api):
            docker("rm", "-f", container, check=False)
        docker("volume", "rm", volume, check=False)
        docker("network", "rm", network, check=False)


if __name__ == "__main__":
    baseline = os.environ.get("PRUCE_BASELINE_IMAGE")
    if baseline:
        scenario(baseline, "baseline", baseline=True)
    scenario(IMAGE, "new")
    scenario(IMAGE, "existing", existing=True)
    print("CLOUD BOOTSTRAP CHECK PASSED (isolated transport; no live iMessage/model claim)")
