# WhatsApp PRUCÊ — preparação e ativação

Auditoria em 17/09/2026. POC de **um usuário**, WhatsApp desligado por padrão.
Sem conta autenticada, commit, push, publicação ou reinício do agente ativo.

## Integração existente e versão

Hermes instalado: **0.21.2**, confirmado pelo metadata Python no container.
Base Plow preservada: `80ef5024eb4b770e727a618a9b55421c73da6228`, digest
`sha256:864771e8165db16c11a55635df85696f39d91020f258576dd62b7cab0515514f`.
O Dockerfile oficial dessa base usa Hermes upstream por digest
`sha256:66300578dbad1937e71288e26116219e7702da07fe5218afdf87423fa51fa0b8`.
Não há `.git` em `/opt/hermes`; não atribuímos um commit Hermes não verificável.

Código auditado na imagem:

- `/opt/hermes/plugins/platforms/whatsapp/{plugin.yaml,adapter.py}`: plugin oficial NousResearch.
- `/opt/hermes/scripts/whatsapp-bridge/bridge.js`: Node + Baileys **7.0.0-rc13**, WhatsApp Web.
- `gateway/platforms/whatsapp_common.py`, `gateway/whatsapp_identity.py`: identidade/políticas.
- `gateway/session.py`, `tools/cronjob_job_args.py`, `cron/scheduler_delivery.py`: sessões/origem/entrega.

Também existe `whatsapp_cloud`, adapter separado da API oficial Meta Business
(token, phone number ID e webhook). Não foi escolhido para o pairing deste POC.
“Oficial Hermes” não significa que Baileys seja uma API oficial da Meta.
Referências: [plugin](https://github.com/NousResearch/hermes-agent/blob/main/plugins/platforms/whatsapp/plugin.yaml),
[guia upstream](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/whatsapp.md),
[base fixada](https://github.com/plow-pbc/plow-hermes-agent/blob/80ef5024eb4b770e727a618a9b55421c73da6228/Dockerfile).
O código instalado, e não `main`, é a autoridade para esta preparação.

## Preparado sem conta

- `npm ci` usa o lockfile embarcado, sem atualizar pins. Dependências: Baileys,
  Express, qrcode-terminal, Pino; Node/npm já presentes (Node 26.5.1 no runtime auditado).
  aiohttp e psutil já disponíveis. Stamp oficial evita `npm install` em runtime.
- Adapter oficial supervisiona seu próprio bridge; não criamos sidecar nem adapter.
- API HTTP do bridge em **127.0.0.1:3000**, sem porta publicada.
- `whatsapp-init` após `plow-init`, antes do gateway, prepara a pasta privada,
  pertencente ao usuário `hermes`, modo 0700, no volume `agent-home` existente.
  Caminho novo: `/var/lib/hermes/platforms/whatsapp/session`. Resolver oficial
  respeita sessão legada populada em `/var/lib/hermes/whatsapp/session`.
- Modo `bot`: Claro é o número do PRUCÊ; Vinicius conversa de seu WhatsApp pessoal.
  Allowlist é o **remetente pessoal**, não o novo número Claro do bot.
- DMs `allowlist`, grupos `disabled`, allow-all `false`, sem debug/encaminhamento
  de mensagens digitadas pelo próprio bot. Allowlist vazia nega acesso.
- Validação exige um único telefone em dígitos (DDI+DDD+número). `*`, múltiplos
  usuários ou destino home diferente são recusados. Em boot, configuração inválida
  desativa só WhatsApp no ambiente s6 e registra o motivo; não bloqueia Plow.
- `whatsapp.env.example`: template sem número fictício ativo. Não contém credenciais.
  `whatsapp.env` é ignorado pelo git e pelo build context.
- `pruce-whatsapp-pair` chama o **bridge oficial com `--pair-only`**, usando o resolver
  de pasta oficial e umask 077. É só um wrapper; não altera `.env` do Hermes/Plow.

Imagem local de preparação: `pruce-whatsapp-check:local`. A imagem não substitui
automaticamente o container ativo. A ativação abaixo faz a troca uma vez, com o
mesmo volume. Não foi feito deploy cloud; One Click mantém base, entrypoint,
Agent Index, credenciais e contrato existentes. Para cloud, a imagem alterada
precisa ser publicada/deployada separadamente, com estas variáveis no host.

## Comandos exatos quando a Claro ativar — deployment Compose local

Primeiro registrar o número Claro no aplicativo WhatsApp/WhatsApp Business no
telefone, confirmar SMS/ligação e abrir **Aparelhos conectados**. eSIM ativo sozinho
não registra uma conta WhatsApp. Mantenha o telefone com internet.

```sh
cd /Users/vinicius/Developer/pruce-hackathon/pruce-hermes-agent
cp -n whatsapp.env.example whatsapp.env
chmod 600 whatsapp.env
open -e whatsapp.env
```

Preencha `WHATSAPP_ALLOWED_USERS` com seu telefone pessoal, só dígitos.
Opcional: `WHATSAPP_HOME_CHANNEL` com esse mesmo telefone seguido de
`@s.whatsapp.net`. **Deixe `WHATSAPP_ENABLED=false` durante o pairing.**
Não altere o arquivo de credenciais Plow existente.

```sh
docker tag pruce-agent:latest pruce-before-whatsapp:local
docker tag pruce-whatsapp-check:local pruce-agent:latest
docker compose --env-file whatsapp.env config --quiet
docker compose --env-file whatsapp.env up -d --no-build --no-deps agent
docker compose --env-file whatsapp.env exec --user hermes agent pruce-whatsapp-pair
```

A troca de imagem reinicia brevemente o gateway único. O volume, sessões,
estado, cron e identidade são preservados. Não use `down -v`.

O terminal mostra um QR. No WhatsApp **da conta Claro do bot**:
**Configurações → Aparelhos conectados → Conectar aparelho → escanear QR**.
Use outra tela para exibir o QR. O bridge salva credenciais/chaves na pasta
persistente e sai quando conecta. Aguarde a confirmação; Ctrl+C cancela se necessário.
Não execute dois pairings/bridges sobre a mesma sessão.

Agora abra `whatsapp.env`, mude somente `WHATSAPP_ENABLED=true` e execute:

```sh
docker compose --env-file whatsapp.env up -d --no-build --no-deps agent
docker compose --env-file whatsapp.env logs --tail=100 agent
docker compose --env-file whatsapp.env exec --user hermes agent node -e 'fetch("http://127.0.0.1:3000/health").then(r=>r.json()).then(x=>console.log(x.status))'
```

Esperado: `connected`. O adapter recusa ativação sem `creds.json`; não fabricamos
esse arquivo. Log do bridge: `/var/lib/hermes/platforms/whatsapp/bridge.log`
(ou equivalente legado). `hermes whatsapp` é o wizard upstream; optamos pelo
entry point oficial `--pair-only` para evitar que o wizard reescreva o dotenv
root-owned desta imagem Plow. QR/chaves/logs são privados; não os publique.

## Testar Oi, RU e cron

Do **WhatsApp pessoal allowlisted**, enviar ao número Claro:

1. `Oi` — deve responder no mesmo DM. Confirme também que iMessage continua respondendo.
2. `O que tem no RU II hoje?` — consulta pelo leitor existente; verifique data/RU
   contra a fonte. Se não publicado/indisponível, deve comunicar isso sem inventar.
3. `Me manda o RU II daqui a 5 minutos.` — deve confirmar agendamento, sem mandar
   o menu imediatamente. Se pedir fuso, confirme horário de Brasília.
   Aguarde 5 minutos com gateway conectado: menu deve chegar nesse WhatsApp.

Para inspecionar o agendamento sem criar outro:

```sh
docker compose --env-file whatsapp.env exec --user hermes agent /opt/hermes/.venv/bin/python3 /var/lib/hermes/skills/pruce-ru/scripts/subscription.py <<'JSON'
{"action":"status"}
JSON
```

`status` lista assinaturas recorrentes; para conferir o job pontual, use a ferramenta
Hermes `cronjob(action="list")` na conversa e confirme destino `whatsapp:<chat_id>`
e execução única. Nunca cole `jobs.json` inteiro em logs públicos.
RU consulta a fonte **na execução**, sem modelo. Menu não publicado/indisponível
fica silencioso no envio agendado; ausência de mensagem nessa condição não prova
falha do transporte. Para separar transporte da fonte, peça também:
`Daqui a 5 minutos me manda a mensagem teste WhatsApp.`

## Origem, sessões e limite de um usuário

Bridge entrega `senderId`, `chatId`, nome, flag de grupo e aliases de identidade.
Adapter cria `SessionSource` com plataforma `whatsapp`, usuário = sender e
conversa = chat. Hermes normaliza identidades/JIDs e DMs têm chave
`<namespace>:whatsapp:dm:<chat_id canônico>`; números diferentes têm rotas/sessões
separadas. Isso separa conversa, **não os dados do produto**. LID e telefone
dependem do mapeamento aprendido pela sessão Baileys; valide o remetente real.

Hermes injeta `HERMES_SESSION_PLATFORM`, `CHAT_ID`, `USER_ID`, `CHAT_TYPE` no
terminal. RU captura isso, persiste `origin` e `deliver=whatsapp:<chat_id>` no
job nativo. Cron resolve o destino e usa o adapter ativo (ou sender standalone
oficial). `WHATSAPP_HOME_CHANNEL` é fallback para jobs genéricos; RU não depende
dele. Corrigimos só o envio pontual: não herda mais destino de assinatura
recorrente iMessage. Alterações de assinatura recorrente continuam preservando
o destino estabelecido. Não há migração automática entre canais; uma troca
exige atualizar o destino do job identificado, preservando os demais jobs.

`/var/lib/hermes/pruce/state.json` continua compartilhado: `introduced`, contexto,
perfil/onboarding, fuso, RU preferido, progresso/consentimento `profile.ru_delivery`,
tarefas, prioridades e follow-through. Também são comuns os ledgers de operações,
fontes, memória, cron/assinatura RU gerenciada, arquivos e acesso Google/Plow.
Outro usuário poderia ler/mudar informações do dono, cancelar envios ou acionar
integrações com sua autoridade. **Não abrir a allowlist nem grupos.**

Menor evolução futura: um Hermes/deployment e volume por dono, com credenciais,
estado, memória, cron e bridge próprios. Para vários donos atendidos pelo mesmo
número, seria preciso roteamento confiável por sender e escopo por dono em todos
esses recursos antes de abrir acesso. Não implementado neste POC.

## Desligar/reverter

Abra `whatsapp.env`, coloque `WHATSAPP_ENABLED=false`, então:

```sh
docker compose --env-file whatsapp.env up -d --no-build --no-deps agent
```

Isso desliga o adapter/bridge e preserva sessão e iMessage/Plow; há o breve reinício
do gateway único. Jobs WhatsApp já existentes continuam no cron: pause/cancele
somente seus IDs com a ferramenta `cronjob` antes de desligar, se quiser evitar
tentativas de entrega. Não cancele indiscriminadamente assinaturas RU iMessage.
Para revogar login: remova o aparelho conectado no aplicativo da conta Claro.
Não apague o volume nem o estado canônico. Para reverter a imagem inteira,
com WhatsApp já desligado no arquivo:

```sh
docker tag pruce-before-whatsapp:local pruce-agent:latest
docker compose --env-file whatsapp.env up -d --no-build --no-deps agent
```

## Validação sem conta e riscos restantes

Resultado desta preparação: **215 testes passaram**, self-check do Agent Index
passou, smoke/persistência/segurança/grafo s6 passaram, Compose válido e diff sem
erros de whitespace. O container ativo não foi reiniciado. Não validamos serviços
externos nem publicação One Click.

```sh
PRUCE_TEST_IMAGE=pruce-whatsapp-check:local python3 -B tests/run_in_image.py
python3 -B tests/check_whatsapp_runtime.py
docker compose config --quiet
git diff --check
```

Testes: contratos reais do Hermes, allowlist oficial Node, preflight sem credenciais,
dependências sem instalação em runtime, separação de sessões/canais, origem cron,
RU pontual com assinatura iMessage já existente, bridge HTTP real em rede desativada,
volume isolado entre containers, permissões, fechamento de WhatsApp inválido e grafo s6.
Markers de persistência são sintéticos e não imitam credenciais.
Suite existente cobre RU, Agent Index offline, estado, operações, fontes e persona.
Não são testes E2E de WhatsApp, iMessage ou Google Workspace.

Restam exclusivamente conta/telefone: registro WhatsApp, QR/login, identidade real
do remetente, reconexão autenticada e testes de entrega/cron reais. Baileys é
WhatsApp Web não oficial Meta, sujeito a mudanças, logout/restrições de conta;
esta versão é RC. Internet de saída é necessária; não há webhook público.
Sem isolamento de donos. Jobs `all` genéricos podem alcançar o home WhatsApp quando
configurado; prefira destinos explícitos. Não migramos nem reescrevemos jobs antigos.

## Arquivos alterados/adicionados

- `Dockerfile`, `.dockerignore`, `.gitignore`, `compose.yml`, `README.md`.
- `whatsapp.env.example`, `docs/WHATSAPP.md`.
- `image/whatsapp_init.py`, `image/whatsapp_pair.sh`.
- `image/s6-overlay/s6-rc.d/whatsapp-init/type`, `whatsapp-init/up`,
  `whatsapp-init/dependencies.d/plow-init`.
- `image/s6-overlay/s6-rc.d/hermes-gateway/dependencies.d/whatsapp-init`,
  `image/s6-overlay/s6-rc.d/user/contents.d/whatsapp-init`.
- `skills/pruce-ru/scripts/subscription.py` (somente destino de envio pontual).
- `tests/test_whatsapp.py`, `tests/check_whatsapp_runtime.py`,
  `tests/test_ru_subscription.py`, `tests/run_in_image.py`.
- `whatsapp.env` local ignorado: template desativado, sem autenticação.
