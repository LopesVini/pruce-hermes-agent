"""Static contracts for Prucê's product-specific decision layer."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PERSONA = (ROOT / "runtime/persona.md").read_text()
ONBOARDING = (ROOT / "skills/pruce-onboarding/SKILL.md").read_text()
TASKS = (ROOT / "skills/pruce-tasks/SKILL.md").read_text()
TRIAGE = (ROOT / "skills/pruce-triage/SKILL.md").read_text()
README = (ROOT / "README.md").read_text()


def normalized(value):
    return " ".join(value.split()).casefold()


class ProductBehaviorTests(unittest.TestCase):
    def test_triage_is_bundled_in_the_variant(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        dockerignore = (ROOT / ".dockerignore").read_text()
        self.assertIn("/opt/hermes/skills/pruce-triage", dockerfile)
        self.assertIn("!skills/pruce-triage/SKILL.md", dockerignore)
        installed = Path("/opt/hermes/skills/pruce-triage/SKILL.md")
        if installed.exists():
            self.assertEqual(installed.read_bytes(),
                             (ROOT / "skills/pruce-triage/SKILL.md").read_bytes())

    def test_onboarding_delivers_value_before_profile(self):
        self.assertIn("Value comes before profile", ONBOARDING)
        self.assertIn("several responsibilities", ONBOARDING)
        self.assertIn("do not pitch integrations in the introduction", ONBOARDING)
        self.assertIn("Accept real tasks immediately", PERSONA)

    def test_multiple_outcomes_remain_independent_open_loops(self):
        self.assertIn("each as its own", TASKS)
        self.assertIn("pruce-triage", TASKS)
        self.assertIn("small validated json open-loop record", normalized(README))

    def test_prioritization_uses_judgment_without_exposing_a_score(self):
        for signal in ("urgency", "consequence of delay", "dependencies",
                       "effort and time", "how long", "stated goals"):
            self.assertIn(signal, TRIAGE)
        self.assertIn("Do not expose a score", TRIAGE)
        self.assertIn("ask one focused question", TRIAGE)

    def test_life_scan_is_on_demand_and_source_honest(self):
        self.assertIn("Known-context scan", TRIAGE)
        self.assertIn("Connected-source scan", TRIAGE)
        self.assertIn("only when its tools are actually connected", TRIAGE)
        self.assertIn("State exactly what the scan covered", TRIAGE)
        self.assertIn("This is an on-demand scan", TRIAGE)
        self.assertIn("do not promise continuous monitoring", normalized(TRIAGE))

    def test_context_only_scan_discloses_coverage_once_and_offers_one_source(self):
        triage = normalized(TRIAGE)
        self.assertIn("if only known context was available", triage)
        self.assertIn("this is not a complete scan yet", triage)
        self.assertIn("offer at most one relevant integration", triage)
        self.assertIn("not in unrelated conversations", triage)

    def test_permissions_are_contextual_and_do_not_expand_authority(self):
        self.assertIn("Offer access only when it unlocks an immediate", TRIAGE)
        self.assertIn("A declined offer ends that offer", TRIAGE)
        self.assertIn("reading permission does not imply permission", normalized(TRIAGE))
        self.assertIn("never ask for passwords, tokens or credentials", normalized(TRIAGE))

    def test_single_user_boundary_is_explicit(self):
        self.assertIn("one person's agent", PERSONA)
        self.assertIn("owner's one-to-one chat", README)
        self.assertIn("Sharing a line, credential, or home volume", README)

    def test_readme_is_english_and_explains_the_product(self):
        self.assertIn("The personal agent for the things you need to deal with", README)
        self.assertIn("Student Life + Adulting", README)
        self.assertIn("open loop", README)
        self.assertIn("progressive onboarding", normalized(README))
        self.assertIn("Agent Index reporting is opt-in", README)


if __name__ == "__main__":
    unittest.main()
