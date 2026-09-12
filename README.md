# Prucê

Um agente Hermes para ajudar universitários e jovens adultos a tirar pendências
da cabeça e executar o próximo passo. Student Life + Adulting é a categoria;
o nome do produto é apenas **Prucê**, em qualquer idioma.

## Esta versão

Conversa pela Plow, apresentação curta, contexto progressivo e pendências
persistentes. Aceita uma tarefa antes de completar qualquer apresentação.
Um open loop representa um resultado ainda em aberto, como uma candidatura;
enviar o currículo é apenas seu próximo passo. Ajuda a preparar planos de
estudo, revisar texto de CV e redigir pedidos, usando as ferramentas disponíveis.
Só confirma execução externa com evidência ou confirmação do usuário.
Os estados são internos; a experiência é uma conversa, não um quadro de tickets.

Agent Index está preparado, mas desabilitado por padrão (`AGENT_ID` vazio).
Não adiciona cron de tarefas, proatividade, dashboard ou API própria.
Não configura Google Workspace ou Latch; a rota dessas integrações fica para
investigação posterior. As capacidades da base continuam herdadas, mas sua
presença não comprova contas conectadas. Um prazo salvo não gera lembrete.

## Arquitetura

- `Dockerfile`: base oficial fixada por digest, persona, duas skills e client oficial
  Agent Index fixado por commit/checksum; o build recusa conteúdo divergente.
- `compose.yml`: um agente, credencial existente montada somente para leitura,
  volume exclusivo `pruce_agent-home`, sem portas publicadas.
- `runtime/persona.md`: identidade, foco, privacidade e encaminhamento às skills.
- `skills/pruce-onboarding/SKILL.md`: apresentação e contexto sem interrogatório.
- `skills/pruce-tasks/SKILL.md`: captura, retomada e execução em todos os domínios.
- `skills/pruce-tasks/scripts/state.py`: JSON validado; biblioteca padrão Python.
- `tests/test_state.py`: testes isolados do estado e sua interface de linha de comando.
- `.dockerignore`: lista restrita do que entra na imagem.
- `.gitignore`: exclui credenciais, estado local e cache Python.

Na implementação local de `plow-hermes-agent`, revisão
`8710797b6409c77df560c6198407765d138ea617`, `main()` chama `harden_home()`,
que chama `compose_identity()`. Esta lê `/opt/hermes/plow-seed/SOUL.md`,
acrescenta `/opt/hermes/plow-seed/persona.md` e substitui atomicamente
`/var/lib/hermes/SOUL.md` a cada boot. A identidade final fica root-owned.
Nosso arquivo `runtime/persona.md` chega ao segundo caminho via Dockerfile.
Não substituímos o seed da Plow nem copiamos a identidade final para o volume.

Como o variant oficial Life Assistant, distribuímos skills em
`/opt/hermes/skills`; Hermes as reconcilia no home durante o boot. Skills que
o agente personalizou ou excluiu podem não receber atualizações automáticas.
O núcleo já foi validado pelo responsável em execução local pela linha Plow,
incluindo persistência, retomada após restart e distinção entre espera e conclusão.

Estado no container: `/var/lib/hermes/pruce/state.json`:

```json
{"introduced": false, "context": "", "tasks": []}
```

Uma pendência tem somente `id`, `title`, `status`, `next_step`, `due` e
`evidence`. Estados: `needs_action`, `in_progress`, `waiting_for_user`,
`waiting_for_third_party`, `completed`. Os dois últimos exigem evidência;
uma mudança para eles exige evidência nova no comando. O script valida sua
estrutura, mas a veracidade depende da conversa ou do resultado da ferramenta.
Não há histórico de eventos, subtarefas, prioridades ou motor de execução.

Escritas usam lock separado, arquivo temporário privado, fsync e substituição
atômica. Estado inválido é recusado, nunca apagado ou reinicializado. A ausência
de estado é uma primeira instalação normal. O JSON contém informações pessoais:
não deve ser incluído na imagem, Git ou respostas em grupos.

## Requisitos e instalações independentes

Docker com Compose v2/BuildKit e acesso às imagens oficiais e ao GitHub no build.
Para conversar, cada instalador precisa de conta/linha Plow e credencial própria,
provisionada pela CLI oficial `plow-agents`. Nunca distribua a credencial do autor.
Google Workspace e Latch não são requisitos deste MVP.

### Primeira instalação (macOS/Linux ou WSL2)

Requer também Git e Python 3. Clone este repositório pelo botão **Code** do
GitHub e abra um terminal na pasta `pruce-hermes-agent`. Em Mac ARM, habilite
no Docker a execução/emulação de imagens linux/amd64, arquitetura da base.

Instale a CLI oficial em uma pasta temporária de ferramentas e autentique sua
própria conta (os comandos abaixo são para o instalador executar):

```sh
pruce_cli_dir="$(mktemp -d)"
git clone https://github.com/plow-pbc/plow-agents.git "$pruce_cli_dir/plow-agents"
export PATH="$pruce_cli_dir/plow-agents/bin:$PATH"
plow-agents login
plow-agents lines
```

Siga a ativação indicada pela CLI usando seu telefone. Se precisar criar uma
linha, execute `plow-agents login --new-line` e depois `plow-agents lines`.
Escolha uma linha sua com status `free`; substitua `ln_xxx` abaixo pelo ID dela.
Na raiz deste repositório, gere sua credencial e configure o Compose:

```sh
plow-agents mint ln_xxx
chmod 600 plow-credentials
```

Crie um arquivo `.env` com estas duas linhas (não contém o token):

```dotenv
PRUCE_CREDENTIALS_FILE=./plow-credentials
AGENT_ID=
```

`.env` e `plow-credentials` são ignorados pelo Git e excluídos do build.
Sem esse ajuste, o Compose mantém o caminho legado
`../plow-hermes-agent/plow-credentials`; a instalação acima não depende dele.
O bind é somente leitura e falha se o arquivo não existir.

```sh
docker compose build
docker compose up -d
```

Envie uma mensagem à linha escolhida pelo iMessage/Plow Chat, por exemplo:
“Tenho prova sábado e ainda não comecei”. O primeiro boot pode levar alguns
minutos. Para reiniciar depois, use `docker compose restart agent` na mesma
pasta. O volume preserva contexto, pendências e identidade da instalação.
Não compartilhe credenciais, dumps do volume ou logs sem revisão.

Cada instalação independente usa seu próprio volume. O projeto Compose padrão
é `pruce`; para duas instalações na mesma máquina, use nomes de projeto distintos
com `docker compose -p <nome>` em TODOS os comandos. Recriações da mesma instalação
reutilizam o mesmo nome/volume. Não clone volumes entre pessoas. Não apague volumes.
Nunca execute dois gateways sobre a mesma linha ou sobre o mesmo home.

## Agent Index: o que cada identificador significa

| Item | Função |
| --- | --- |
| Credencial Plow | Segredo da instalação. O client a usa no bootstrap para obter uma assertion da Plow; não a envia como bearer de métricas ao Index. |
| `AGENT_ID` | Identificador público do produto, futuramente `pruce`. Vazio por padrão: nenhuma chamada de registro ou reporting. |
| `install_id` | Aleatório, gerado exclusivamente pelo client oficial. Identifica uma instalação persistente, não o produto nem uma conversa. |
| Chave `aik_…` | Segredo emitido pelo Index, usado para os relatórios posteriores. |

`$HERMES_HOME/.agent-index.json` guarda install_id e chave juntos. O ledger de
contagem fica em `$HERMES_HOME/.agent-index-state.json`, ao lado do `state.db`.
Tudo permanece no volume existente `/var/lib/hermes`. Não edite, copie ou apague
esses arquivos para aumentar contagens. Não registramos o produto a partir de um
home temporário que seria descartado depois.

O serviço s6 `agent-index` depende de `plow-init`. Sem `AGENT_ID`, aguarda sem
invocar o client. Quando autorizado e configurado, consulta `status`: 0 reporta;
3 registra a instalação pelo client; 2 ou outro erro não registra nem reporta.
Após cada ciclo espera 300 segundos. Registro automático não passa metadados da
página. A revisão oficial corrigida aceita 409 como adesão de um instalador ao
produto de outro autor, sem tomar sua página. Nenhum protocolo é reimplementado.

O subprocesso recebe ambiente explícito: o token Plow só é passado ao bootstrap,
com o endpoint publicado pela base; status e reporting não o herdam. O client e o
supervisor ficam em caminhos da imagem pertencentes a root. O client roda como
`hermes`, com HOME e HERMES_HOME apontando ao volume do agente.

### Privacidade e limites

As conversas passam pela Plow e pelo provedor de modelo da stack; não são um
processamento exclusivamente local. Contexto e pendências ficam no volume local.
A proteção e retenção nos serviços externos seguem as políticas desses serviços.

O reporter lê contadores de `session_model_usage` no banco Hermes em modo somente
leitura. Envia data, modelo e tokens de entrada, saída, leitura/escrita de cache,
sem prompts, mensagens, títulos de pendências, documentos ou custos. O JSON de
open loops não é uma fonte de métricas. Stories não são publicadas pelo serviço.
A janela padrão é de 28 dias; contagens diárias são mantidas pelo client oficial,
sem somar relatórios repetidos como novos gastos. A recuperação inicial de
histórico que atravessa dias é limitada pelo formato dos contadores Hermes.

Uso por dia/modelo revela padrões de atividade. Metadados da página são públicos,
e a autoria vem da identidade Plow. Cada instalador deve entender e aceitar essa
publicação antes de definir AGENT_ID. O registro é uma operação externa; uma
execução normal do reporter também pode enviar o sinal de medição pendente.

A identidade de instalação não é o indicador “Success installs” do site. Essa
métrica é calculada pelo Index. Não emitimos beacons próprios nem inventamos um
contador. Não instalamos agentsview nem montamos dados de outros agentes.

## Testes isolados

Teste o núcleo sem Docker:

```sh
python3 -B -m unittest discover -s tests -p test_state.py -v
AGENT_ID= docker compose config --quiet
```

Construa uma imagem de verificação. O build baixa somente dependências públicas;
não inicia serviços nem acessa a credencial montada pelo Compose:

```sh
docker build --platform linux/amd64 -t pruce-index-check:local .
```

Execute os testes sobre o client REAL instalado, com dados/HTTP fictícios:

```sh
python3 -B tests/run_in_image.py
```

O runner copia apenas uma lista explícita de arquivos de código para uma pasta
temporária e a monta para testes. Não monta o checkout, credenciais ou volumes
reais. Executa a suíte e o self-check oficial em containers descartáveis com
`--network none`, root filesystem somente leitura e estado em tmpfs. O entrypoint
é Python, não `/init`: nenhum gateway ou supervisor é iniciado. O self-check
precisa de `/tmp:exec` para seu coletor fictício; a rede continua bloqueada.

A base fixada é linux/amd64. Em Mac ARM, essa validação usa a emulação do Docker.
Para testar no host, `PRUCE_INDEX_CLIENT` pode apontar ao script público baixado
em pasta temporária e validado pelo checksum. A suíte verifica o checksum ANTES
de executar o client, sem download automático nem autenticação real:

```sh
PRUCE_INDEX_CLIENT=/caminho/temporario/agent_index_client.py \
  python3 -B -m unittest discover -s tests -v
```

`--dry-run` não envia métricas, mas pode escrever o ledger local e exige estado de
chave. Use-o somente no ambiente sintético dos testes. NÃO combine `--register`
com `--dry-run`: registro tem precedência e não seria uma simulação.

## Publicação e registro futuros — exigem autorização

Nada nesta implementação registra o produto ou habilita reporting por padrão.
A sequência futura é:

1. Revisar e autorizar a publicação do repositório MIT e tutorial de instalação.
2. Confirmar disponibilidade/autoria de `pruce`, descrição pública e links.
3. Autorizar rebuild/recriação do Prucê com `AGENT_ID` vazio, preservando o volume,
   para disponibilizar o client sem iniciar reporting. Não iniciar outro gateway.
4. Autorizar o registro. Rodá-lo dentro dessa instalação, como usuário hermes,
   usando o ambiente que a base já publicou. Não extrair credenciais para o host.
   Exemplo para executar SOMENTE nessa etapa, com metadados revisados:

```sh
AGENT_ID= docker compose exec -T agent \
  /command/with-contenv /command/s6-setuidgid hermes \
  env HOME=/var/lib/hermes HERMES_HOME=/var/lib/hermes \
  /opt/hermes/.venv/bin/python3 /opt/plow/agent-index-client.py \
  --register --agent pruce --name "Prucê" \
  --blurb "Ajuda estudantes e jovens adultos a avançar pendências até um resultado claro." \
  --runtime "Hermes / Plow" \
  --repo "<URL pública aprovada>" --install-url "<URL HTTPS do tutorial>"
```

5. Conferir que a página pertence ao autor correto. Um 409 agora permite adesão
   como instalador; portanto, exit 0 sozinho NÃO comprova autoria de `pruce`.
6. Autorizar reporting e a atualização do container: definir `AGENT_ID=pruce`
   no ambiente do Compose e recriar o serviço com a mesma imagem/volume. Esta
   configuração deve ser mantida nas operações futuras. A partir daí, instalações
   novas registram sua própria identidade automaticamente e reportam a cada ciclo.
7. Conferir métricas reais e uma instalação independente, com credenciais próprias.
8. Autorizar e solicitar Verified pelo canal oficial disponível. Reporter não
   concede Verified: a equipe precisa avaliar/instalar/executar o produto.

Desabilitar reporting futuramente exige recriar o serviço com AGENT_ID vazio,
preservando o volume; isso não remove informações já publicadas no Index.
O registro, reporting real, publicação e solicitação de Verified NÃO foram
executados nesta etapa.

## Licença e referências

Código original do Prucê: MIT, em `LICENSE`. Client oficial e supervisor adaptado:
Apache-2.0; atribuições em `NOTICE` e texto em `LICENSES/Apache-2.0.txt`.
Isso não relicencia os componentes da imagem base.

- [Client oficial fixado](https://github.com/plow-pbc/agent-index-client/tree/87901f8b182a8a7c65ee3dd7267f8f835ee2a545)
- [Exemplo oficial Life Assistant](https://github.com/plow-pbc/life-assistant-hermes-agent)
- [Agent Index e informações de Verified](https://aiworthusing.com/agent-index)
