# Prucê

Um agente Hermes para ajudar universitários e jovens adultos a tirar pendências
da cabeça e executar o próximo passo. Student Life + Adulting é a categoria;
o nome do produto é apenas **Prucê**, em qualquer idioma.

## Esta versão

Conversa pela Plow, apresentação curta, contexto progressivo e pendências
persistentes. Aceita uma tarefa antes de completar qualquer apresentação.
Os estados são internos; a experiência é uma conversa, não um quadro de tickets.

Não adiciona integrações, Agent Index, cron, proatividade, dashboard ou API.
Não configura Google Workspace ou Latch; a rota dessas integrações fica para
investigação posterior. As capacidades da base continuam herdadas, mas sua
presença não comprova contas conectadas. Um prazo salvo não gera lembrete.

## Arquitetura

- `Dockerfile`: base oficial fixada por digest, persona e duas skills.
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
Essa reconciliação ainda precisa ser observada no primeiro boot do Prucê.

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

## Testes locais, sem container

A partir deste repositório:

```sh
python3 -B -m unittest discover -s tests -v
docker compose config --quiet
```

Os testes usam diretórios temporários e não acessam credenciais nem o home do
Hermes. A validação de Compose não inicia serviços. Esses testes não validam
conversa com o modelo, entrega Plow, build da imagem ou boot.

## Primeiro teste pela linha existente — ainda não executado

Primeiro construa a imagem; este comando não assume a linha:

```sh
docker compose build
```

**Só depois de autorizar a troca**, com a imagem construída, pare o gateway
oficial e inicie o Prucê. Nunca mantenha ambos ativos com a mesma credencial:

```sh
docker stop plow-hermes-agent-agent-1
docker compose up -d
```

O Compose referencia `../plow-hermes-agent/plow-credentials` sem copiar ou
imprimir seu conteúdo. `create_host_path: false` faz um caminho ausente falhar
em vez de criar uma pasta. Não faça mint. Não apague volumes. O estado do
Hermes oficial permanece separado e preservado. O histórico remoto da Plow
pode continuar disponível; volume novo não significa conversa remota vazia.

Se for necessário voltar ao Hermes oficial, pare o Prucê primeiro:

```sh
docker compose stop
docker start plow-hermes-agent-agent-1
```

No teste conversacional, use a linha já funcional e confira:

1. Saudação: apresenta-se como Prucê, explica o propósito e faz uma pergunta curta.
2. Tarefa como primeira mensagem: ajuda imediatamente, sem exigir perfil.
3. Experimente prova de termodinâmica, aproveitamento de matéria, cancelamento
   de assinatura e envio de CV. O mesmo fluxo deve atender a todos.
4. Dê contexto em etapas: deve lembrar as respostas e pedir apenas o necessário.
5. Peça retomada em outra sessão e após reiniciar somente o Prucê: deve recuperar
   a pendência, sem duplicá-la. Reiniciar o container, sozinho, pode restaurar
   a sessão anterior; teste uma sessão distinta também.
6. Verifique que plano ou rascunho não vira conclusão de uma tarefa mais ampla.
   Confirme um resultado realizado e peça uma atualização posterior.

Não prometa notificações nem execução enquanto o container estiver parado.
