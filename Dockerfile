FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-8710797b6409c77df560c6198407765d138ea617@sha256:b9627febe57e34ec0df373709ad91a27a7fda68093e76d519678cac1012614f9

# plow-init composes the base SOUL plus this persona on every boot.
COPY --chmod=0644 runtime/persona.md /opt/hermes/plow-seed/persona.md
# Follow the official variant: Hermes reconciles bundled skills into its home.
COPY skills/ /opt/hermes/skills/
RUN chmod 0755 /opt/hermes/skills/pruce-onboarding /opt/hermes/skills/pruce-tasks /opt/hermes/skills/pruce-tasks/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-onboarding/SKILL.md /opt/hermes/skills/pruce-tasks/SKILL.md /opt/hermes/skills/pruce-tasks/scripts/state.py
