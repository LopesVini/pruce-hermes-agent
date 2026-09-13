FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-8710797b6409c77df560c6198407765d138ea617@sha256:b9627febe57e34ec0df373709ad91a27a7fda68093e76d519678cac1012614f9

# plow-init composes the base SOUL plus this persona on every boot.
COPY --chmod=0644 runtime/persona.md /opt/hermes/plow-seed/persona.md
# Follow the official variant: Hermes reconciles bundled skills into its home.
COPY skills/ /opt/hermes/skills/
RUN chmod 0755 /opt/hermes/skills/pruce-onboarding /opt/hermes/skills/pruce-sources /opt/hermes/skills/pruce-sources/scripts /opt/hermes/skills/pruce-triage /opt/hermes/skills/pruce-tasks /opt/hermes/skills/pruce-tasks/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-onboarding/SKILL.md /opt/hermes/skills/pruce-sources/SKILL.md /opt/hermes/skills/pruce-sources/scripts/sources.py /opt/hermes/skills/pruce-triage/SKILL.md /opt/hermes/skills/pruce-tasks/SKILL.md /opt/hermes/skills/pruce-tasks/scripts/state.py

# Product licensing and attribution for the unmodified official client and
# adapted Life Assistant supervisor. Neither credentials nor install IDs ship.
COPY LICENSE NOTICE /usr/share/doc/pruce/
COPY LICENSES/ /usr/share/doc/pruce/LICENSES/
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client checksum mismatch" >&2; exit 1; }; \
    chmod 0644 /opt/plow/agent-index-client.py
COPY image/s6-overlay/ /etc/s6-overlay/
RUN chmod 0755 /etc/s6-overlay/s6-rc.d/agent-index/run
