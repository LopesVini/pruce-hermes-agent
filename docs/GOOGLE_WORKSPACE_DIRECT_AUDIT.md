# Google direto no PRUCÊ — auditoria de viabilidade

17/09/2026. Hermes instalado **0.21.2**; mesma base Plow fixada no Dockerfile.
Escopo: um dono por deployment, Gmail/Calendar independentes do canal.

## Conclusão

**As APIs e os scripts oficiais Hermes podem rodar em Linux/headless sem Mac.**
**O PRUCÊ atual não oferece “instalar → autorizar Google → usar” para usuário
comum em One Click.** Não ativamos uma integração parcial nem escrevemos OAuth
próprio. Não alteramos One Click, Compose, Dockerfile, plugin, persona, RU,
Google/Latch existentes, estado ou container nesta investigação.

Há duas camadas distintas na mesma imagem:

| Camada instalada | Comportamento |
|---|---|
| Skill `google-workspace` ativa, versão 2.5.0 | Variante oficial Plow: Gmail/Calendar pelo Mac/Latch; proíbe OAuth local e não possui tokens Google neste deployment. |
| Scripts oficiais Hermes ainda embarcados | OAuth direto e chamadas Google, com client fornecido pelo operador. A presença deles não os torna uma integração ativa do PRUCÊ. |

A documentação do Hermes upstream descreve o caminho direto. Porém encontramos
divergência: o `SKILL.md` em `main` menciona `--services`/`--format`, enquanto o
script instalado **não aceita esses argumentos**. Não copiamos comandos de
documentação mais nova para esta imagem, nem atualizamos pins especulativamente.

Fontes locais auditadas, sem leitura de segredos:

- `/opt/hermes/skills/productivity/google-workspace/SKILL.md` e cópia ativa em
  `/var/lib/hermes/skills/productivity/google-workspace/SKILL.md`.
- `/opt/hermes/skills/productivity/google-workspace/scripts/setup.py`,
  `google_api.py`, `_hermes_home.py`, `gws_bridge.py`.
- `/opt/hermes/plugins/plow_chat/__init__.py`, `/etc/s6-overlay/scripts/plow-init.py`.
- `skills/pruce-triage/SKILL.md`, README e contrato cloud do PRUCÊ.

Referências oficiais: [skill Hermes](https://github.com/NousResearch/hermes-agent/blob/main/skills/productivity/google-workspace/SKILL.md),
[setup Hermes](https://github.com/NousResearch/hermes-agent/blob/main/skills/productivity/google-workspace/scripts/setup.py),
[Google Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Google Web OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).
O código instalado foi a autoridade para os comandos abaixo.

## Como funciona OAuth nos scripts embarcados

1. Operador cria projeto Google Cloud, habilita APIs, configura consentimento e
   fornece arquivo OAuth client (o guia upstream pede tipo **Desktop app**).
2. `setup.py --client-secret PATH` valida o JSON e copia para o Hermes home.
3. `--auth-url` gera URL com `access_type=offline`, `prompt=consent`, state e PKCE.
4. Usuário abre a URL num browser próprio. O servidor não precisa de browser.
5. Redirect fixo **`http://localhost:1`**, sem listener/callback HTTP criado pelo
   script. No browser, localhost é o dispositivo do usuário, não a VM Linux.
   O fluxo upstream pede copiar manualmente a URL da página que falhou.
6. `--auth-code URL_OU_CODE` troca o código no servidor via HTTPS e salva token.
7. `google_api.py` usa bibliotecas Google, carrega token e faz refresh automático.
   Se `gws` existir, usa-o com esse mesmo token via
   `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`. `gws` não está instalado e não é exigido.

Isso é um caminho técnico de operador, não um callback hospedado nem um botão
“Conectar Google”. Não usamos esse retorno manual como solução de produto.
Não concluímos que Google rejeita toda autorização desse tipo: não houve tentativa
real. O blocker comprovado é o fluxo hospedado **ausente**, não o Linux.
O fluxo Web oficial Google usa redirect registrado e handler para receber a
autorização; Desktop loopback é documentado com listener local. A configuração
JSON `web` é aceita pelo script, mas o redirect continua fixo em localhost:1.

Estado OAuth é validado quando a URL traz state divergente; o código também aceita
code isolado/URL sem state, e o pending não tem TTL no arquivo. Isso não fornece
o contrato completo de associação browser → dono → deployment de um onboarding
cloud público. Não inventamos um handler ou token broker para suprir isso.

## Persistência e isolamento

Todos os caminhos usam `HERMES_HOME`, que nesta base é `/var/lib/hermes`:

| Arquivo | Conteúdo |
|---|---|
| `google_client_secret.json` | Configuração do OAuth client |
| `google_oauth_pending.json` | State, verifier PKCE, redirect da autorização pendente |
| `google_token.json` | Access/refresh token, client e scopes concedidos |

Ficam no volume do deployment, não na imagem. A base auditada não possui código
que resete esses arquivos em boot. Não há necessidade de Google no estado canônico
`pruce/state.json`. Um deployment isolado pode ter sua própria conta; nenhum
selector multiusuário ou multi-tenancy foi criado.

No deployment ativo, verificamos **apenas existência**: os três arquivos estão
ausentes. Nenhuma credencial real foi lida, copiada ou criada.
Os scripts escrevem arquivos com permissões derivadas do umask; não impõem 0600
nem cifram os JSONs. Uma implementação futura deve assegurar home privado,
arquivos 0600 e política de backup. Testes usaram umask 077 em volume descartável.

## Blockers reais para o objetivo de usuário comum

1. **Client OAuth do produto ausente neste caminho:** Hermes não entrega um
   client pré-configurado para este setup; o fluxo exige arquivo do operador.
   Pedir que cada usuário crie projeto Google Cloud não cumpre o onboarding pedido.
2. **Callback cloud ausente:** não há endpoint OAuth Google no deployment/One
   Click identificado nesta auditoria; o script só usa retorno manual localhost:1.
   Não alteramos provisionamento nem expomos API/dashboard para improvisar callback.
3. **Scopes incompatíveis com o recorte atual:** o script instalado tem lista
   fixa: Gmail readonly/send/modify, Calendar completo, Drive completo, Contacts
   readonly, Sheets e Docs. Não há flag para Gmail/Calendar somente leitura.
   Desmarcar permissões na tela não transforma Calendar completo em readonly.
4. **Roteamento atual força Mac:** a skill Plow manda usar relay. O plugin também
   injeta `LATCH_PROMPT` quando existe `PLOW_MCP_URL`, exigindo primeira leitura no
   Mac e proibindo substituição pelo servidor se desconectado. PRUCÊ triage segue
   essa regra. Apenas instalar tokens/adicionar uma skill não prova uso direto;
   desligar o relay afetaria outras capacidades e não foi feito.

O passo mínimo futuro é obter um **caminho oficial suportado** para autorização
hosted/headless, client de produto, scopes adequados e precedência Google direto
com Latch preservado para demais capacidades. Depois, registrar a rota no PRUCÊ
e testar consentimento/refresh/API de verdade. Não é necessário refatorar RU,
Agent Index, canais ou estado canônico para isso.

## Canal e integração do dono

O código `google_api.py` não depende de iMessage/WhatsApp. Após conexão direta
correta, Gmail/Calendar seriam capacidades do deployment do dono, acionáveis por
qualquer canal autorizado. O canal fornece pedido/resposta, não as credenciais
Google. Os scripts não demonstram por si só quem está autorizado em cada canal;
continuam necessários owner/allowlist e grupos restritos. Mantemos um dono.

## Exigências externas para One Click — sem mudanças nesta tarefa

- Provisionar client/app OAuth apropriado, habilitar Gmail e Calendar APIs e
  definir quem administra projeto e consentimento.
- Confirmar fluxo oficial de autorização e callback seguro, associação ao dono,
  entrega das credenciais ao volume isolado e reconexão/revogação.
- Escolher Gmail leitura e Calendar leitura, preservando ações externas desativadas.
- Garantir `/var/lib/hermes` persistente/isolado, permissões e saída HTTPS para Google.
- Resolver roteamento oficial Google direto sem desligar Plow/Latch.

Gmail readonly é scope **restricted**. Uma aplicação pública precisa avaliar
verificação e requisitos de segurança; o Google documenta security assessment
para armazenamento/transmissão de dados de scopes restricted em servidores.
Não assumir que volumes isolados eliminam essas obrigações.
[Escopos Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes).
Refresh tokens de app External em Testing normalmente expiram em 7 dias com
esses scopes; Testing não equivale a conexão durável de produção.
[Política de refresh tokens](https://developers.google.com/identity/protocols/oauth2).

## Testes executados e limites

**220 testes passaram**, incluindo os 215 anteriores e 5 testes Google oficiais
offline; self-check do Agent Index passou. Testes Google rodam na imagem, com rede
desativada e homes temporários:

- Dependências exatas do setup já instaladas: Google API client 2.194.0,
  google-auth 2.55.1, oauthlib client 1.3.1, auth-httplib2 0.3.1,
  httplib2 0.32.0, pyasn1 0.6.4. Nenhuma instalação/upgrade necessário.
- URL real construída pela biblioteca OAuth, com client **fictício e não funcional**,
  state/PKCE/offline request; não houve autorização nem exchange de token.
- Callback com state errado rejeitado antes da troca.
- Paths de client/pending/token seguem home; outro home não vê client/token.
- CLI oficial Gmail search e Calendar list recusam execução sem token, sem Mac.
- Client/pending fictícios sobreviveram a **substituição de container** no mesmo
  volume descartável, com arquivos 0600. Isso valida armazenamento de client e
  pending; não prova validade/persistência/refresh de credencial autenticada.

**Não executados:** login Google, listar eventos reais, buscar email real, refresh,
restart do deployment autenticado, E2E dos canais. Não há client/token autorizado
para esses testes. Container ativo mantido sem reinício; integração Plow preservada
por ausência de mudanças runtime, não por um novo teste live Plow/Latch.
WhatsApp permanece com a preparação da tarefa anterior; não foi ativado.

## Comandos exatos para validar localmente agora

Imagem já preparada na tarefa WhatsApp, com os scripts Google originais intactos:

```sh
cd /Users/vinicius/Developer/pruce-hackathon/pruce-hermes-agent
PRUCE_TEST_IMAGE=pruce-whatsapp-check:local python3 -B tests/run_in_image.py
python3 -B tests/check_google_workspace_storage.py
git diff --check
```

Inspecionar argumentos reais no container existente, sem setup/restart:

```sh
docker compose exec --user hermes agent /opt/hermes/.venv/bin/python3 /opt/hermes/skills/productivity/google-workspace/scripts/setup.py --help
docker compose exec --user hermes agent /opt/hermes/.venv/bin/python3 /opt/hermes/skills/productivity/google-workspace/scripts/setup.py --check
```

Neste deployment sem token, `--check` retorna `NOT_AUTHENTICATED`, exit 1.
Com token existente, `--check` pode executar refresh e persistir o token atualizado.

Após um client/fluxo de consentimento seguro ser aprovado e credenciais reais
serem provisionadas, os comandos **read-only** da CLI instalada para smoke são:

```sh
docker compose exec --user hermes agent /opt/hermes/.venv/bin/python3 /opt/hermes/skills/productivity/google-workspace/scripts/setup.py --check-live
docker compose exec --user hermes agent /opt/hermes/.venv/bin/python3 /opt/hermes/skills/productivity/google-workspace/scripts/google_api.py calendar list --calendar primary --max 10
docker compose exec --user hermes agent /opt/hermes/.venv/bin/python3 /opt/hermes/skills/productivity/google-workspace/scripts/google_api.py gmail search 'newer_than:7d' --max 5
```

Calendar list sem datas usa agora até 7 dias à frente; flags reais para janela são
`--start`/`--end`, não `--from`/`--to` do cabeçalho antigo. Não executar restart
agora para simular persistência de tokens que não existem. Quando houver conexão
real e uma janela de restart, repetir esses reads depois de `docker compose restart
agent` preservando o mesmo volume e verificar refresh quando o access token expirar.
Nunca imprimir JSON de tokens nem enviá-lo por chat.

## Perguntas para Daniel/Plow — não enviadas

1. Existe integração Google **server-side oficial**, fora de Latch, disponível
   para custom agents no One Click? Qual API/skill e qual versão suporta isso?
2. Plow fornece app OAuth Google/consentimento verificado ou cada produto precisa
   de projeto/client próprio? O que já cobre Gmail restricted scopes?
3. Qual fluxo oficial recebe o callback e associa conta Google a owner/deployment?
   Pode provisionar token nesse volume sem Mac e sem usuário operar Google Cloud?
4. Há scopes separados para Gmail readonly e Calendar readonly e revogação/reconnect?
5. Qual hook/config oficial permite Google direto mantendo `PLOW_MCP_URL` para
   demais capacidades, sem `LATCH_PROMPT` forçar mail/calendar no Mac?
6. Como o usuário/operador acessa setup privado da VM One Click? Qual garantia de
   persistência, permissões, backups e descarte das credenciais ao remover deployment?

Sem resposta documentada não atribuímos à Plow capacidades de backend não públicas.

## Arquivos desta tarefa

- `docs/GOOGLE_WORKSPACE_DIRECT_AUDIT.md` (este relatório).
- `tests/test_google_workspace.py` (contratos offline dos scripts oficiais).
- `tests/check_google_workspace_storage.py` (volume descartável entre containers).
- `tests/run_in_image.py` (adiciona explicitamente o novo arquivo ao bundle).
- `README.md` (link para esta auditoria).

Mudanças WhatsApp anteriores preservadas. Sem commit, push ou alteração de memória.
