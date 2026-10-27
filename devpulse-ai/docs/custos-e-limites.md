# Custos, limites e dependências externas

Nenhum serviço externo foi tratado como gratuito. Os valores abaixo são **estimativas** feitas em outubro de 2026. Confira sempre a tabela oficial de cada provedor antes de ativar um serviço.

## Resumo

| Item | Necessário? | Custo esperado | Controle no DevPulse |
|---|---|---|---|
| Execução local (Docker Desktop, PostgreSQL) | Sim | Sem custo de serviço; usa CPU, RAM (~500–800 MB nos 4 containers) e disco (dezenas de MB/mês de dados) | Retenção feita pelo próprio banco; `make backup` |
| Feeds RSS/Atom, páginas públicas | Sim | Gratuito | Intervalo por fonte; recuo progressivo em falhas; ETag/Last-Modified |
| APIs públicas (Hacker News/Algolia, CISA KEV, GitHub REST) | Opcional | Gratuitas com limites: a API do GitHub sem token permite cerca de 60 req/h por IP | `fetch_interval_minutes` 240–360 min nas fontes de API; `GITHUB_TOKEN` opcional |
| Gmail API / Microsoft Graph / IMAP | Para ler a newsletter | Sem cobrança para uso pessoal dentro das cotas | Lê só mensagens do remetente, no máximo 5 por coleta, a cada 120 min |
| Serviços de extração de conteúdo | Não usado | — | A extração é local (BeautifulSoup); no máximo 25 páginas por edição (`max_extractions_per_run`) |
| API de IA | Opcional | Ver abaixo | **Efetivo:** limite diário de chamadas e de tokens de saída. **Estimado:** custo em US$ |
| E-mail de saída (SMTP) | Para o canal e-mail | Gmail/Outlook pessoais: sem cobrança, com limites diários de envio; provedores transacionais têm planos gratuitos limitados | 1 e-mail por edição, até 5 tentativas |
| WhatsApp Business Platform | Para o canal WhatsApp | Cobrança da Meta por mensagem de template entregue, com preço por categoria (utilidade/marketing) e país | 1 mensagem por edição; sem reenvio automático em caso de dúvida |

## IA (estimativa por roteiro)

Uma geração com IA envia até 4 fontes (≈ 12 mil caracteres cada) e recebe um pacote JSON completo:

- entrada: ~8 mil a 20 mil tokens;
- saída: ~4 mil a 10 mil tokens, incluindo o raciocínio adaptativo do modelo;
- uma revisão extra quando a checagem reprova a primeira versão (pior caso: 2 chamadas por roteiro);
- uma chamada de pontuação por edição, com o modelo econômico (`LLM_MODEL_FAST`).

Preços de referência da Anthropic (US$ por milhão de tokens, entrada/saída, outubro de 2026):

| Modelo | Uso sugerido | Preço | Estimativa por roteiro | 3 roteiros/dia por 30 dias |
|---|---|---|---|---|
| `claude-opus-5-5` (padrão) | Roteiros | 4 / 20 | ~US$ 0,11–0,28 (até ~0,56 com revisão) | ~US$ 10–25 (pior caso ~50) |
| `claude-sonnet-5-5` | Roteiros, opção mais econômica | 2 / 10 | ~US$ 0,06–0,14 | ~US$ 5–13 |
| `claude-haiku-5-5` (padrão para pontuação) | Pontuação/classificação | 0,10 / 0,50 | < US$ 0,01 por edição | < US$ 0,30 |

Esses números dependem do tamanho real das fontes e de quantas revisões acontecem. O painel mostra, por dia, as chamadas feitas e o **custo estimado**, calculado com `LLM_PRICE_INPUT_PER_MTOK`/`LLM_PRICE_OUTPUT_PER_MTOK`. Ajuste esses dois valores se mudar de modelo. Se usar Sonnet nos roteiros, por exemplo, defina 2.0 e 10.0.

**O que é efetivo e o que é estimativa:**

- **Efetivo** (aplicado pelo DevPulse antes de cada chamada): `LLM_MAX_CALLS_PER_DAY` e `LLM_MAX_OUTPUT_TOKENS_PER_DAY`. Ao atingir o limite, a edição continua com o roteiro-base extrativo e registra o motivo.
- **Efetivo no provedor**: limites de gasto mensal configuráveis no console da Anthropic (Limits / Spend limits). Recomendado como segunda barreira.
- **Estimativa**: o valor em dólares exibido no painel. A fatura oficial é a do provedor.

**Sem custo de IA**: `LLM_PROVIDER=none` (roteiro-base extrativo) ou um modelo local via Ollama (`LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://host.docker.internal:11434/v1`). Modelos locais menores tendem a falhar mais na checagem de trechos literais; nesses casos, o sistema cai para o roteiro-base.

## WhatsApp

Desde julho de 2025, a Meta cobra **por mensagem de template entregue**, com preço variando por categoria e pelo país do destinatário. Mensagens de serviço respondidas dentro da janela de 24 h aberta pelo usuário seguem regras próprias. Tabela atual: <https://developers.facebook.com/docs/whatsapp/pricing>. Com 1 mensagem por dia, o volume mensal é de ~30 templates.

## Limites operacionais do DevPulse

- Até 3 roteiros por dia (validado na configuração e no painel; não passa de 3).
- Até 25 páginas abertas por edição para extração.
- Fontes que falham entram em recuo progressivo (intervalo × 2, 4, 8… até 24×).
- Respostas HTTP acima de 5 MB são descartadas.
