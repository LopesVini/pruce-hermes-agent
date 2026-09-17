# Base source 80ef5024eb4b770e727a618a9b55421c73da6228 pins
# hermes-plugin-plow at 8e055e059ce774b455869d915525e63933db18fe.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-80ef5024eb4b770e727a618a9b55421c73da6228@sha256:864771e8165db16c11a55635df85696f39d91020f258576dd62b7cab0515514f

# Cloud deploy runs the image directly, without the local Compose environment.
ENV AGENT_ID=pruce

# Official Hermes bridge, installed from its shipped lockfile; no custom adapter.
RUN cd /opt/hermes/scripts/whatsapp-bridge \
 && npm ci --omit=dev --no-audit --no-fund \
 && /opt/hermes/.venv/bin/python3 -c 'import hashlib,pathlib; p=pathlib.Path("."); (p/"node_modules/.hermes-pkg-hash").write_text(hashlib.sha256((p/"package.json").read_bytes()).hexdigest()[:16])'
ENV WHATSAPP_ENABLED=false WHATSAPP_MODE=bot \
    WHATSAPP_ALLOW_ALL_USERS=false WHATSAPP_DM_POLICY=allowlist \
    WHATSAPP_GROUP_POLICY=disabled WHATSAPP_ALLOWED_USERS="" \
    WHATSAPP_FORWARD_OWNER_MESSAGES=false WHATSAPP_DEBUG=false
COPY --chmod=0644 image/whatsapp_init.py /opt/plow/whatsapp-init.py
COPY --chmod=0755 image/whatsapp_pair.sh /usr/local/bin/pruce-whatsapp-pair

# Omit native cron headers only for authenticated Prucê RU delivery records.
COPY --chmod=0644 image/patch_ru_delivery.py /opt/plow/patch-ru-delivery.py
RUN /opt/hermes/.venv/bin/python3 -B /opt/plow/patch-ru-delivery.py

# plow-init composes the base SOUL plus this persona on every boot.
COPY --chmod=0644 runtime/persona.md /opt/hermes/plow-seed/persona.md
# Follow the official variant: Hermes reconciles bundled skills into its home.
COPY skills/ /opt/hermes/skills/
RUN chmod 0755 /opt/hermes/skills/pruce-ru /opt/hermes/skills/pruce-ru/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-ru/SKILL.md /opt/hermes/skills/pruce-ru/scripts/menu.py /opt/hermes/skills/pruce-ru/scripts/subscription.py /opt/hermes/skills/pruce-ru/scripts/daily.py /opt/hermes/skills/pruce-ru/scripts/request.py
RUN chmod 0755 /opt/hermes/skills/pruce-drafting /opt/hermes/skills/pruce-onboarding /opt/hermes/skills/pruce-operations /opt/hermes/skills/pruce-sources /opt/hermes/skills/pruce-sources/scripts /opt/hermes/skills/pruce-triage /opt/hermes/skills/pruce-tasks /opt/hermes/skills/pruce-tasks/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-drafting/SKILL.md /opt/hermes/skills/pruce-onboarding/SKILL.md /opt/hermes/skills/pruce-operations/SKILL.md /opt/hermes/skills/pruce-sources/SKILL.md /opt/hermes/skills/pruce-sources/scripts/sources.py /opt/hermes/skills/pruce-triage/SKILL.md /opt/hermes/skills/pruce-tasks/SKILL.md /opt/hermes/skills/pruce-tasks/scripts/operations.py /opt/hermes/skills/pruce-tasks/scripts/state.py

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
