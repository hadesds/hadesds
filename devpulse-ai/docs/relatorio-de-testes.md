# Relatório de testes e pendências

Data: 27/10/2026. Ambiente de desenvolvimento: container Linux com Python 3.13, Node 22 e PostgreSQL 16 locais, **sem daemon Docker** e com saída de rede restrita por proxy (a maioria dos domínios de notícias estava bloqueada).

As categorias abaixo separam o que foi **testado de verdade**, o que foi **testado com simulação** e o que **depende de configuração externa**.

## 1. Resultados

| Conjunto | Comando | Resultado |
|---|---|---|
| Backend: unitários | `pytest tests/unit` | 44 aprovados |
| Backend: integração (PostgreSQL real) | `pytest tests/integration` | 25 aprovados |
| Backend: serviços externos | `RUN_EXTERNAL_TESTS=1 pytest tests/external` | 1 aprovado (feed real do Node.js); 2 pulados (envios reais exigem autorização explícita) |
| Painel: unitários/componentes | `npm test` (Vitest + Testing Library) | 6 aprovados |
| Painel: tipos | `npm run typecheck` | sem erros |
| Painel: build de produção | `npm run build` | ok |
| Navegador real (Chromium/Playwright) | login → painel → fontes → notícias → roteiros → detalhe → edição → configurações | todas as telas carregaram, edição salva, 0 erros de console |
| Migração | `alembic upgrade head` + `alembic check` | aplicada; modelo e migração idênticos |
| Compose | `docker compose config` | válido |

## 2. Critérios de aceitação

| # | Critério | Como foi demonstrado | Tipo |
|---|---|---|---|
| 1 | Fonte real cadastrada e consultada | 26 fontes de `config/sources.yaml` cadastradas no PostgreSQL. Coleta real de **Node.js Blog** (30 itens) e **Anthropic News** (15 itens). `test_create_and_list_source` (API) | **Real** + integração |
| 2 | Notícia coletada tem URL e data de origem | Itens reais com `published_at` vindo do feed ou dos metadados do artigo, distinto de `discovered_at`. `test_item_keeps_url_and_original_dates`, `test_rss_items_have_url_and_original_date` | **Real** + integração |
| 3 | Duplicatas identificadas | `test_duplicate_by_url_across_sources_adds_reference`, `test_same_external_id_is_not_duplicated`, `test_similar_titles_are_grouped_in_same_cluster`, `test_different_versions_are_different_events` | Integração |
| 4 | No máximo 3 roteiros por edição diária | `test_edition_respects_limit_and_produces_complete_scripts`, `test_daily_limit_is_shared_across_runs`, `test_daily_limit_cannot_exceed_three` | Integração |
| 5 | Cada roteiro tem falas, cenas e sugestões visuais | Mesmos testes + roteiro real em [examples/roteiro-exemplo-anthropic-s1.md](examples/roteiro-exemplo-anthropic-s1.md) | **Real** + integração |
| 6 | Afirmações centrais com referências verificáveis | `FactCheck` central `supported` com `source_url`. No exemplo real, os trechos foram encontrados na página e o link respondeu HTTP 200 | **Real** + integração |
| 7 | Sem fontes adequadas, não há fabricação | `test_no_adequate_sources_means_no_fabricated_scripts` (0 roteiros; e-mail "nenhuma notícia suficientemente verificada"). `test_unsupported_llm_claim_triggers_revision_then_fallback` | Integração (IA simulada) |
| 8 | E-mail enviado com provedor real | Código SMTP pronto. `tests/external/test_real_email_send` e o botão "Enviar teste" do painel existem, mas **não foram executados**: não havia credenciais SMTP neste ambiente | **Pendente de credenciais** |
| 9 | WhatsApp integrável com credenciais/aprovações | Adaptador da Cloud API pronto. Montagem de template e interpretação de respostas da Meta testadas com respostas simuladas. **Nenhum envio real** | Simulado; **pendente de conta Meta** |
| 10 | Falha de um canal não afeta o outro | `test_channel_failure_is_isolated` (e-mail `failed_auth`, WhatsApp `sent`). `test_retryable_failure_schedules_backoff` | Integração (transportes simulados) |
| 11 | Reiniciar não duplica a edição | `test_rerun_after_restart_does_not_duplicate`, `test_interrupted_send_goes_to_review_not_resent`, `test_run_checkpoints_are_persisted`. Worker real iniciado duas vezes: uma única execução `edition:2026-10-27:main` | Integração + **processo real** |
| 12 | Tarefas pendentes recuperadas | `test_stale_running_run_is_resumed`, `test_recovery_window`, `test_old_pending_editions_expire`. O worker real criou e processou a edição perdida das 08:00 ao iniciar às 12:46 (dentro da janela até 14:00) | Integração + **processo real** |
| 13 | Painel consulta fontes, notícias, roteiros e entregas | `test_dashboard_news_scripts_deliveries` + navegação real no Chromium | Integração + **navegador real** |
| 14 | Testes não enviam mensagens reais sem autorização | `test_real_sends_blocked_in_tests`. O `conftest` bloqueia rede e SMTP. Envios reais só com `RUN_EXTERNAL_TESTS=1` **e** `ALLOW_REAL_SENDS_IN_TESTS=true` | Unitário |

## 3. Problemas encontrados e corrigidos durante a validação real

- **Respostas compactadas** (gzip/brotli) eram descompactadas duas vezes e a coleta falhava. Corrigido em `http.py`, com teste `test_rss_handles_gzip_content_encoding`.
- **Releases diferentes agrupadas juntas** (Node.js 26.11.0 × 26.11.1). Corrigido com regra de versões em `similarity.py`.
- **Frases cortadas em abreviações** ("U.S. Securities"). Corrigido em `sentences()`.
- **O roteiro-base escolhia a frase institucional** ("Anthropic is an AI safety company…") em vez do fato. Agora as frases são ordenadas pela relação com o título.
- **Datas sem horário** apareciam no dia anterior. Agora são interpretadas no fuso `America/Fortaleza`.
- **Os checkpoints da execução** (`scheduled_runs.stats`) não eram persistidos após a primeira etapa, porque o ORM não detectava a reatribuição do mesmo dict. Corrigido, com teste de regressão.
- **A recuperação inicial do worker** rodava antes dos tratadores de sinal. Ela agora roda dentro do agendador.

## 4. O que NÃO foi testado neste ambiente

| Item | Motivo | Como validar no seu computador |
|---|---|---|
| `docker compose up` e build da imagem | Sem daemon Docker neste ambiente | `make up` e depois `make ps` (os 4 serviços `running`/`exited 0` para `migrate`) e http://localhost:8080 |
| `make test` dentro do container | Idem | `make test` |
| Coleta da maioria das fontes (GitHub, OpenAI, Python, Go, Rust, Kubernetes, CISA, HN…) | Bloqueadas pelo proxy deste ambiente (HTTP 403 do proxy) | Painel → Fontes → "Coletar" em cada uma. Falhas aparecem na coluna "Situação" com o erro |
| Docker Blog | O site recusou o cliente HTTP do DevPulse com 403 (respondeu ao `curl`). O sistema registra a recusa e não tenta contorná-la | Verifique no seu computador; se continuar 403, desative a fonte |
| Leitura da TechDrops | Sem caixa de e-mail configurada. A coleta registra "Nenhuma caixa de e-mail configurada" | [configuracao-email.md](configuracao-email.md) e depois Fontes → TechDrops → Coletar |
| O formato real do HTML da TechDrops | Não havia edições disponíveis; o parser foi testado com HTML de exemplo | Depois da primeira coleta, confira em Notícias se os títulos e links extraídos fazem sentido |
| Geração com IA real | Sem chave de API neste ambiente. O caminho da IA foi testado com um cliente simulado (validação, checagem, revisão, limite diário, remoção de links) | Configure `LLM_PROVIDER=anthropic` + `LLM_API_KEY` e gere uma edição pelo painel |
| Envio real de e-mail e WhatsApp | Sem credenciais/conta Meta | "Enviar teste" no painel ou `RUN_EXTERNAL_TESTS=1 ALLOW_REAL_SENDS_IN_TESTS=true pytest tests/external` |
| Gmail API / Graph OAuth | Sem contas | `scripts/oauth_gmail.py` ou `scripts/oauth_graph.py` |

## 5. Exemplo gerado a partir de notícia real

- Roteiro: [examples/roteiro-exemplo-anthropic-s1.md](examples/roteiro-exemplo-anthropic-s1.md). Fonte: <https://www.anthropic.com/news/s1-sec>, coletada pelo conector `webpage` e verificada (trechos e link) em 27/10/2026.
- E-mail renderizado: [examples/email-exemplo.html](examples/email-exemplo.html).
- Mensagem de WhatsApp (modos texto e template): [examples/whatsapp-exemplo.txt](examples/whatsapp-exemplo.txt). Gerada, **não enviada**.

O exemplo foi produzido **sem IA** (roteiro-base extrativo), porque não havia chave de API. Por isso as falas trazem trechos em inglês e um espaço para a sua análise. Com a IA configurada, o mesmo pipeline produz falas originais em português, e cada afirmação continua sujeita à mesma checagem contra a fonte.
