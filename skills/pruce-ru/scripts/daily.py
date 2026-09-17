"""Hermes no_agent entry: current published lunch or empty stdout, never an LLM."""
from pathlib import Path
import argparse
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("daily_subscription", Path(__file__).with_name("subscription.py"))
subscription = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subscription)


def render(jobs=None, query=None, once_key=None):
    jobs = jobs if jobs is not None else subscription.native_runtime()[0].list_jobs(include_disabled=True)
    active = [job for job in jobs if subscription.configuration(job)
              and job.get("enabled", True) and not job.get("paused", False)]
    active = [job for job in active if
              (subscription.configuration(job).get("key") == once_key if once_key else
               subscription.configuration(job)["kind"] == subscription.MARKER)]
    if len(active) != 1:
        return ""  # Ambiguous/removed subscriptions fail closed.
    config = subscription.configuration(active[0])
    if config.get("opt_in") is not True:
        return ""
    result = (query or subscription.menu.query)(ru=config["ru"], when="hoje", meal="almoço")
    return result["text"] if result.get("status") == "ok" and result.get("items") else ""


def main(once_key=None):
    try:
        text = render(once_key=once_key)
        if text:
            print(text)
    except Exception:
        # Missing/corrupt configuration or a source failure is silent. Native
        # scheduler retains its run history; no repeated failure DM.
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once-key")
    main(parser.parse_args().once_key)
