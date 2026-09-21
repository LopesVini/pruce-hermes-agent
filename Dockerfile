# Base source ef0019372ff8bca593611b31ebd2e08f9f1458ff pins
# hermes-plugin-plow at c21aa5aaefac7d2de3fa47ac46c69f40c2efc68a.
# It also ships the Agent Index reporter (pinned client + s6 service), which
# reads AGENT_ID below; this repo carries no reporter of its own.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-ef0019372ff8bca593611b31ebd2e08f9f1458ff@sha256:a8a2f97ad78b8192d80a984dce81d3bf5a9a883d18cb7b677704913a09b56aee

# Cloud deploy runs the image directly, without the local Compose environment.
ENV AGENT_ID=pruce
# Keep the runtime defaults used before the reporter migration. The new base
# otherwise selects GLM-5.2 and a Los Angeles clock for this variant.
ENV HERMES_MODEL=anthropic/claude-sonnet-5 HERMES_TIMEZONE=UTC

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
RUN chmod 0755 /opt/hermes/skills/pruce-watch /opt/hermes/skills/pruce-watch/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-watch/SKILL.md /opt/hermes/skills/pruce-watch/scripts/watch.py
RUN chmod 0755 /opt/hermes/skills/pruce-ru /opt/hermes/skills/pruce-ru/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-ru/SKILL.md /opt/hermes/skills/pruce-ru/scripts/menu.py /opt/hermes/skills/pruce-ru/scripts/subscription.py /opt/hermes/skills/pruce-ru/scripts/daily.py /opt/hermes/skills/pruce-ru/scripts/request.py
RUN chmod 0755 /opt/hermes/skills/pruce-drafting /opt/hermes/skills/pruce-onboarding /opt/hermes/skills/pruce-operations /opt/hermes/skills/pruce-sources /opt/hermes/skills/pruce-sources/scripts /opt/hermes/skills/pruce-triage /opt/hermes/skills/pruce-tasks /opt/hermes/skills/pruce-tasks/scripts \
 && chmod 0644 /opt/hermes/skills/pruce-drafting/SKILL.md /opt/hermes/skills/pruce-onboarding/SKILL.md /opt/hermes/skills/pruce-operations/SKILL.md /opt/hermes/skills/pruce-sources/SKILL.md /opt/hermes/skills/pruce-sources/scripts/sources.py /opt/hermes/skills/pruce-triage/SKILL.md /opt/hermes/skills/pruce-tasks/SKILL.md /opt/hermes/skills/pruce-tasks/scripts/operations.py /opt/hermes/skills/pruce-tasks/scripts/state.py

# Product licensing and attribution. Neither credentials nor install IDs ship.
COPY LICENSE NOTICE /usr/share/doc/pruce/
COPY LICENSES/ /usr/share/doc/pruce/LICENSES/
COPY image/s6-overlay/ /etc/s6-overlay/
