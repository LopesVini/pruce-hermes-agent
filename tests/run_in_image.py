"""Test the installed client offline, mounting only an explicit code allowlist.

Build first: docker build --platform linux/amd64 -t pruce-index-check:local .
Run: python3 -B tests/run_in_image.py
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ".dockerignore", "Dockerfile", "README.md", "compose.yml", "runtime/persona.md",
    "vendor/client.pin", "tests/test_agent_index.py", "tests/test_operations.py",
    "tests/test_first_run.py", "tests/test_product_behavior.py",
    "tests/test_sources.py", "tests/test_state.py", "skills/pruce-onboarding/SKILL.md",
    "skills/pruce-operations/SKILL.md",
    "skills/pruce-sources/SKILL.md", "skills/pruce-sources/scripts/sources.py",
    "skills/pruce-triage/SKILL.md", "skills/pruce-tasks/SKILL.md",
    "skills/pruce-tasks/scripts/operations.py",
    "skills/pruce-tasks/scripts/state.py",
    "image/s6-overlay/s6-rc.d/agent-index/run",
    "image/s6-overlay/s6-rc.d/agent-index/type",
    "image/s6-overlay/s6-rc.d/agent-index/dependencies.d/plow-init",
    "image/s6-overlay/s6-rc.d/user/contents.d/agent-index",
)
RUN = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none",
       "--read-only", "--tmpfs", "/tmp:exec", "--tmpfs", "/var/lib/hermes",
       "--tmpfs", "/opt/data", "--env", "HOME=/tmp", "--env", "HERMES_HOME=/var/lib/hermes"]
PYTHON = ["--entrypoint", "/opt/hermes/.venv/bin/python3", "pruce-index-check:local"]


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
