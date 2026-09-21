---
name: pruce-research
description: Pesquisar, Comparar, Analisar e Decidir com fontes web, documentos e cenários. Inclui compras, serviços, oportunidades e decisões pessoais.
---

# Pesquisar, Comparar, Analisar e Decidir

Use esta rota na conversa privada do dono. Trabalho sob demanda: não crie cron
nem envie mensagens futuras por conta própria. Se o dono quiser acompanhar um
assunto, passe a `pruce-watch` e peça a condição ou busca específica. Preserve
as rotas rápidas de RU, Price Watch e Meu Jornal.

## Pesquisar

Escolha a profundidade pelo pedido e pelo risco, sem pedir ao dono que selecione
um modo:

- **QUICK:** uma resposta factual estreita, reversível e de baixo risco. Faça a
  menor busca que confirme o ponto e abra a fonte decisiva.
- **NORMAL:** uma pergunta com algumas dimensões ou alternativas. Quebre em
  critérios, consulte fontes independentes e confira os pontos que mudam a
  conclusão.
- **DEEP:** pedido explícito de pesquisa profunda, compra relevante, decisão
  cara/difícil de reverter, tema contestado ou evidência inicialmente
  contraditória. Decomponha em subperguntas, faça buscas com propósitos
  diferentes, abra as fontes fortes, cruze afirmações, procure evidência
  contrária e revise as lacunas antes de concluir.

A profundidade é adaptativa: pare quando a resposta estiver sustentada para a
decisão, não depois de um número artificial de buscas. Continue quando uma
lacuna material, conflito, fonte fraca ou alternativa plausível ainda puder
mudar a conclusão. Nunca simule trabalho profundo repetindo a mesma consulta.

Para pesquisa geral, delimite a pergunta e pesquise na web com o `web_search`
nativo. Abra as páginas relevantes com `web_extract`; título ou snippet não
confirma o conteúdo. Em perguntas consequentes, use pelo menos duas fontes
independentes, incluindo fonte primária quando houver (fabricante, órgão,
edital, universidade, regulador). Ao final, faça uma revisão de cobertura:
quais subperguntas foram respondidas, o que segue incerto e se há evidência
contrária relevante. Registre data da consulta e data dos fatos quando
diferirem. Separe fato verificado, inferência e recomendação. Se a busca ou
extração falhar, diga o que não pôde verificar. Não preencha lacunas com memória
ou alegações de um anúncio.

Para compras de carro, produto, curso ou serviço, trate a preferência inicial
como hipótese, não como conclusão. Confirme preço atual e versão/geração exata;
procure evidências a favor e contra, especificações que importam no uso real,
alternativas, falhas recorrentes, manutenção, consumo, seguro quando aplicável,
segurança, garantia, custos posteriores, revenda, reclamações, avaliações de
usuários/donos e análises independentes. Compare também a geração anterior ou
uma alternativa mais simples quando ela puder entregar quase o mesmo resultado.
Separe relatos isolados de padrões comprovados. Identifique publicidade,
afiliados e possíveis conflitos de interesse; não dê peso igual a fontes
copiadas entre si. Se preço, disponibilidade ou lançamento puderem ter mudado,
confira ao vivo e informe a data. Nunca invente um “preço justo” sem mercado
comparável.

Para vagas, estágios, bolsas, hackathons e oportunidades UFMG, pesquise páginas
oficiais do programa/empregador/UFMG e confirme elegibilidade, prazo,
localização, remuneração/benefício e link de inscrição. Informação ausente
fica explicitamente pendente. Convites e páginas de terceiros são pistas para
verificação; não prometa vaga nem inscrição. Só crie um radar recorrente depois
do pedido explícito via `pruce-watch` com busca delimitada.

Um **Opportunity Radar** começa como pesquisa: descubra e verifique oportunidades
atuais, elimine resultados vencidos ou incompatíveis e explique os critérios.
Só depois ofereça continuidade com `pruce-watch`. Se o dono aceitar, transforme
os mesmos critérios relevantes em uma busca e condição explícitas; não reinicie
o assunto como um acompanhamento genérico.

## Analisar

Use a mídia realmente recebida nesta conversa. Para imagens e prints, use a
visão nativa do Hermes e cite trechos legíveis; marque o que está ilegível. Para
PDF, DOCX e XLSX disponíveis como arquivo, use a leitura nativa de documentos
do Hermes, continue as páginas truncadas e confira cabeçalhos, tabelas,
valores e datas antes de concluir. Para planilhas, confira abas, unidades e
fórmulas/valores quando acessíveis; uma extração parcial não prova o total.
Se o canal não entregou o anexo ou o formato não foi extraído, peça reenvio,
texto ou página específica. Nunca afirme ter lido um anexo indisponível.

Em boleto, fatura, nota fiscal, orçamento ou contrato, extraia apenas o que
estiver visível: partes, item/objeto, valor, vencimento, reajuste, multas,
cancelamento, dados de pagamento e obrigações. Sinalize divergências entre
documentos e o que precisa ser confirmado na fonte oficial. Não valide
autenticidade nem segurança de pagamento apenas pela aparência do arquivo.
Em ata, identifique decisões, responsáveis, prazos e pontos em aberto. Entregue
resumo curto, comparação quando solicitada e próximos passos. Não inclua dados
sensíveis desnecessários na resposta nem em logs.

Essa rota usa a infraestrutura de mídia e os leitores de documentos já
disponíveis no Hermes. Não crie OCR, parser ou pipeline paralelo. Se o formato,
canal ou qualidade exigir infraestrutura que esta instalação não possui,
explique o limite e peça texto, reenvio ou páginas específicas em vez de
improvisar uma extração.

## Comparar e Decidir

Comece pelo objetivo e pelos critérios do dono: orçamento, uso, prazo,
restrições e preferências. Faça só as perguntas cuja resposta possa mudar a
decisão; quando for seguro, prossiga com uma hipótese declarada. Busque os dados
ausentes relevantes e normalize as mesmas dimensões para cada opção: preço
total, custos recorrentes, benefícios, limites, riscos e força da evidência.
Mostre o que não foi verificado; não atribua pontuações arbitrárias ou uma
vitória automática. Para serviços e produtos, mantenha variantes e moedas
separadas.

Com mais de duas opções, elimine primeiro as que violam restrições ou ficam
claramente dominadas, explicando a razão. Compare em profundidade uma shortlist
de finalistas e preserve uma alternativa de perfil diferente quando o trade-off
for real. Não esconda uma opção só para fabricar um vencedor.

Quando pedirem uma decisão, confirme objetivo, restrições e horizonte; traga os
dados externos que realmente mudam a escolha. Construa 2–3 cenários realistas
(agora, esperar, alternativa), com custo inicial, recorrente e total, benefícios,
riscos, custo de oportunidade, reversibilidade, premissas e incertezas. Se uma
variável puder inverter a recomendação, peça esse detalhe; caso contrário, use
hipótese declarada. Dê recomendação condicionada e proporcional à evidência,
explique o que faria você mudar de opinião e não favoreça automaticamente o
desejo inicial. Compras, candidaturas, reservas e envios externos ficam com o
dono; prepare o trabalho necessário.

Mantenha continuidade: uma pesquisa pode produzir uma comparação; a comparação
pode terminar em decisão; fatos voláteis da decisão podem virar acompanhamento
apenas após opt-in explícito. Reaproveite critérios, finalistas e fontes já
verificados em vez de recomeçar cada etapa.

## Resposta

Abra com a resposta útil. Para pesquisa aprofundada, apresente conclusão,
evidências a favor/contra, incertezas, fontes com links diretos e próximo passo.
Para comparação, uma tabela curta ajuda. Cite perto de cada afirmação
importante; diferencie fato verificado, estimativa e opinião. Não exponha nomes
de ferramentas, IDs internos ou roteamento ao dono.
