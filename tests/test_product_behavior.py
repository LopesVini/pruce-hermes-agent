"""Static contracts for Prucê's product-specific decision layer."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PERSONA = (ROOT / "runtime/persona.md").read_text()
ONBOARDING = (ROOT / "skills/pruce-onboarding/SKILL.md").read_text()
TASKS = (ROOT / "skills/pruce-tasks/SKILL.md").read_text()
TRIAGE = (ROOT / "skills/pruce-triage/SKILL.md").read_text()
SOURCES = (ROOT / "skills/pruce-sources/SKILL.md").read_text()
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

    def test_source_map_is_bundled_separately_from_open_loops(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        dockerignore = (ROOT / ".dockerignore").read_text()
        self.assertIn("/opt/hermes/skills/pruce-sources", dockerfile)
        self.assertIn("!skills/pruce-sources/scripts/sources.py", dockerignore)
        self.assertIn("independent schema and lock", SOURCES)

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

    def test_manual_sources_are_dated_context_not_permanent_coverage(self):
        source_rules = normalized(SOURCES)
        self.assertIn("never perpetual freshness", source_rules)
        self.assertIn("manual observations become stale", source_rules)
        self.assertIn("do not build custom ocr", source_rules)

    def test_connected_map_entry_still_requires_a_live_tool(self):
        source_rules = normalized(SOURCES)
        self.assertIn("verify it before claiming a connected-source scan", source_rules)
        self.assertIn("failed or unavailable tools do not refresh coverage", source_rules)

    def test_supported_integration_is_distinct_from_current_availability(self):
        source_rules = normalized(SOURCES)
        self.assertIn("prucê technically supports that source", source_rules)
        self.assertIn("configured and available in this deployment", source_rules)
        self.assertIn("not connected **in this installation**", source_rules)
        self.assertIn("never say “this version has no integration”", source_rules)

    def test_owner_source_does_not_imply_access_or_capability(self):
        source_rules = normalized(SOURCES)
        self.assertIn("a source-map entry establishes the first fact", source_rules)
        self.assertIn("does not prove the other facts", source_rules)
        self.assertIn("do not promise support merely because the owner uses the source", source_rules)

    def test_access_and_unsupported_claims_require_real_capability_checks(self):
        persona = normalized(PERSONA)
        self.assertIn("never claim access before live verification", persona)
        self.assertIn("call a capability unsupported only after checking", persona)
        self.assertIn("temporary fallback", persona)

    def test_declined_source_offer_is_not_repeated_for_same_context(self):
        triage = normalized(TRIAGE)
        self.assertIn("record that decision and its concrete outcome context", triage)
        self.assertIn("do not repeat the same offer for the same context", triage)

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
