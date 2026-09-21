"""Test the installed client offline, mounting only an explicit code allowlist.

Build first: docker build --platform linux/amd64 -t pruce-index-check:local .
Run: python3 -B tests/run_in_image.py
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "tests/test_watch.py", "skills/pruce-watch/SKILL.md", "skills/pruce-watch/scripts/watch.py",
    "skills/pruce-research/SKILL.md",
    "tests/test_google_workspace.py",
    "tests/test_whatsapp.py", "image/whatsapp_init.py", "whatsapp.env.example",
    "tests/test_ru_delivery.py", "image/patch_ru_delivery.py",
    "tests/test_ru_request.py", "skills/pruce-ru/scripts/request.py",
    "tests/test_ru_subscription.py", "skills/pruce-ru/scripts/subscription.py",
    "skills/pruce-ru/scripts/daily.py",
    "tests/test_ru.py", "skills/pruce-ru/SKILL.md", "skills/pruce-ru/scripts/menu.py",
    ".dockerignore", "Dockerfile", "README.md", "compose.yml", "runtime/persona.md",
    "tests/test_operations.py",
    "tests/test_first_run.py", "tests/test_product_behavior.py",
    "tests/test_runtime_identity.py",
    "skills/pruce-drafting/SKILL.md",
    "tests/test_sources.py", "tests/test_state.py", "skills/pruce-onboarding/SKILL.md",
    "skills/pruce-operations/SKILL.md",
    "skills/pruce-sources/SKILL.md", "skills/pruce-sources/scripts/sources.py",
    "skills/pruce-triage/SKILL.md", "skills/pruce-tasks/SKILL.md",
    "skills/pruce-tasks/scripts/operations.py",
    "skills/pruce-tasks/scripts/state.py",
)
RUN = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none",
       "--read-only", "--tmpfs", "/tmp:exec", "--tmpfs", "/var/lib/hermes",
       "--tmpfs", "/opt/data", "--env", "HOME=/tmp", "--env", "HERMES_HOME=/var/lib/hermes"]
PYTHON = ["--entrypoint", "/opt/hermes/.venv/bin/python3", os.environ.get("PRUCE_TEST_IMAGE", "pruce-index-check:local")]


def main():
    with tempfile.TemporaryDirectory(prefix="pruce-index-bundle-") as tmp:
        for name in FILES:
            target = Path(tmp) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        subprocess.run(RUN + ["--mount", f"type=bind,src={tmp},dst=/workspace,readonly",
                       "--workdir", "/workspace"] + PYTHON +
                       ["-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                       check=True, timeout=120)
    # The upstream self-check creates an executable fake collector in /tmp;
    # hence tmpfs :exec. External networking remains unavailable throughout.
    subprocess.run(RUN + PYTHON + ["/opt/plow/agent-index-client.py", "--self-check"],
                   check=True, timeout=120)


if __name__ == "__main__":
    main()
