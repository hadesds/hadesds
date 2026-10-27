# Plano técnico e arquitetura

## Decisões

| Tema | Escolha | Motivo |
|---|---|---|
| Execução | Docker Compose com 4 serviços (`db`, `migrate`, `api`, `worker`) | Roda no Docker Desktop via WSL2, sem VPS e sem um segundo daemon |
| API + painel | FastAPI servindo o build do React | Um container a menos; o painel e a API ficam na mesma origem (sem CORS em produção) |
| Agendador | APScheduler 3.11, processo próprio (`worker`), job store no PostgreSQL | Persistência dos jobs; a separação da API evita que dois agendadores rodem juntos. Um advisory lock garante um worker só |
| Idempotência | Tabela `scheduled_runs` com `run_key` único (`edition:AAAA-MM-DD:main`) + `notification_deliveries.idempotency_key` único | Reiniciar não duplica a edição nem as mensagens |
| Banco | PostgreSQL 16, SQLAlchemy 2, migrações Alembic versionadas | Restrições únicas fazem a deduplicação valer também no banco |
| IA | Provedor configurável: SDK oficial da Anthropic (padrão), qualquer API compatível com `/chat/completions`, ou nenhum | Custo controlável; o sistema também funciona sem IA |
| Dedup semântica | Combinação lexical (Jaccard, sequência) + termos-chave (nomes próprios, versões) | Determinística, gratuita e testável. Embeddings podem entrar depois sem mudar o fluxo |
| Extração | BeautifulSoup + metadados (Open Graph, JSON-LD, `<time>`) + robots.txt | Sem serviços pagos; respeita restrições de acesso |

## Fases de implementação

Todas as fases abaixo foram implementadas e ficam executáveis:

1. **Fundação**: repositório, Compose, FastAPI, modelos, migração `0001`, configuração por `.env`, testes.
2. **Coleta e curadoria**: RSS/Atom, APIs (Hacker News, CISA KEV, genérica), releases do GitHub, página de listagem, newsletter por IMAP/Gmail API/Microsoft Graph, TechDrops, deduplicação, agrupamento, classificação e pontuação.
3. **Produção editorial**: geração por IA com saída estruturada (JSON Schema) ou roteiro-base extrativo, cenas, guia de gravação, pesquisa de recursos visuais, legenda e checagem.
4. **Entregas**: SMTP, WhatsApp Cloud API, registro de tentativas, retentativas e idempotência.
5. **Interface e operação**: painel, cadastro de fontes, histórico, configurações, agendamento, recuperação e documentação.

## Fluxo de uma edição (`scheduler/pipeline.py`)

Cada etapa grava seu resultado em `scheduled_runs.stats` e pode ser retomada:

1. `collect`: coleta as fontes cujo intervalo venceu (com recuo progressivo para fontes que falham).
2. `enrich`: abre o link original dos candidatos, respeitando robots.txt, sem contornar paywall e com limite por edição. Completa conteúdo, data original, autor, imagens e links citados.
3. `score`: calcula a pontuação de cada agrupamento recente. Com IA disponível, um modelo econômico refina 4 dos 8 critérios (`editorial_scoring/llm_refine.py`).
4. `generate`: seleciona por pontuação, respeitando o limite diário restante, `max_per_category`, a retenção de temas e a elegibilidade. Gera e checa. Um roteiro reprovado é salvo como `rejected`, e o sistema passa para a próxima notícia.
5. `deliver`: cria as entregas (uma por canal) e dispara.

## Critérios editoriais (`editorial_scoring/`)

Pesos da pontuação (0–100): atualidade 18%, relevância para desenvolvedores 18%, confiabilidade 16%, utilidade prática 14%, interesse do público 10%, potencial visual 9%, originalidade 8%, explicabilidade em vídeo curto 7%.

Uma notícia **não é elegível** quando:

- a data de publicação original é desconhecida, ou está fora da janela de atualidade (72 h por padrão). A data de coleta nunca é usada como data de publicação;
- nenhum conteúdo da fonte está acessível;
- é rumor;
- não tem fonte primária (nível ≤ 2) nem duas fontes independentes. Textos quase idênticos em domínios diferentes contam como uma fonte só;
- é de alto impacto (aquisições, demissões, vazamentos, falhas zero-day…) e não tem fonte oficial nem segunda fonte independente;
- fica abaixo da pontuação mínima (55);
- repete um tema já usado no período de retenção (10 dias).

Se nenhuma notícia for elegível, a edição principal envia um resumo informando que não houve notícias suficientemente verificadas, com os principais motivos.

## Checagem (`fact_checking/checker.py`)

- O modelo é obrigado a declarar cada afirmação com `source_ref` e um **trecho literal** da fonte.
- O sistema procura o trecho no texto coletado (igualdade normalizada ou cobertura de trigramas ≥ 90%). Os números e versões da afirmação precisam constar na fonte.
- Números e versões que aparecem nas falas e em nenhuma fonte são sinalizados.
- Os links das fontes são verificados no momento da geração.
- Afirmações centrais sem sustentação → o modelo recebe a lista de problemas e reescreve uma vez. Se falhar de novo, entra o roteiro-base extrativo. A versão sem sustentação nunca é entregue.
- URLs escritas pelo modelo que não constam das fontes ou dos recursos encontrados são removidas.
- "Demonstração executada" escrita pelo modelo é corrigida para "não executada", porque o sistema não executa testes.

O registro de checagem (afirmação, fonte, tipo de evidência, resultado, observações) fica em `fact_checks` e aparece no roteiro, no e-mail e no painel.

## Modelo de dados

`sources`, `source_runs`, `news_items` (datas separadas: `published_at`, `source_updated_at`, `discovered_at`; flag `published_at_inferred` para a data de newsletter), `news_clusters`, `source_references`, `editorial_scores`, `fact_checks`, `scripts`, `script_scenes`, `media_assets`, `notification_deliveries`, `scheduled_runs`, `application_settings` e `llm_usage` (consumo da IA).

Restrições contra duplicação:

- `news_items.normalized_url`, único
- `(news_items.source_id, external_id)`, único
- `(scripts.edition_date, cluster_id)`, único
- `scheduled_runs.run_key`, único
- `notification_deliveries.idempotency_key`, único
- `(source_references.news_item_id, source_id, url)`, único

## Conectores

Interface comum em `source_connectors/base.py`:

```python
from devpulse.source_connectors.base import ConnectorContext, FetchResult, RawItem, SourceConnector
from devpulse.source_connectors.registry import register

@register("minha_api")
class MinhaApi(SourceConnector):
    description = "Exemplo"
    config_fields = {"token_env": "nome da variável com o token"}

    def fetch(self, ctx: ConnectorContext) -> FetchResult:
        r = ctx.http.get(ctx.source_url)
        return FetchResult(items=[RawItem(external_id=i["id"], url=i["link"], title=i["title"],
                                          published_at=...) for i in r.json()])
```

Salve o arquivo num pacote importável (por exemplo, `backend/plugins/minha_api.py`) e defina `PLUGIN_MODULES=plugins.minha_api`. O tipo aparece no painel em "Adicionar fonte".

Tipos incluídos: `rss`, `json_api` (predefinições `hackernews` e `cisa_kev`), `github_releases`, `webpage` e `email_newsletter`.

## Segurança

- Todas as portas ficam em `127.0.0.1`. O painel exige login (usuário e senha do `.env`, token assinado com validade de 12 h, limite de tentativas) e envia cabeçalhos `X-Frame-Options`, `nosniff` e `no-referrer`.
- Credenciais existem só no `.env`. A API informa apenas se cada credencial está presente.
- Logs em JSON passam por um filtro que remove tokens, senhas, chaves e valores de segredos configurados. E-mails e telefones aparecem mascarados.
- A caixa de e-mail é lida em modo somente leitura, e só mensagens do remetente configurado são baixadas.
- O container roda com usuário sem privilégios.
- Testes automatizados bloqueiam rede e envios reais (`APP_ENV=test`).

## Limitações conhecidas

- O status "entregue/lido" do WhatsApp chega por webhook, que exige URL pública. Nesta versão local, o sistema registra só a **aceitação** pela API.
- O SMTP confirma a aceitação pelo servidor, não a chegada à caixa de entrada.
- O link do painel nos e-mails só funciona no computador onde o DevPulse roda.
- A deduplicação semântica é heurística: matérias sobre o mesmo fato com títulos muito diferentes podem ficar em agrupamentos separados.
- Sem IA, os roteiros são roteiros-base em idioma original e precisam de tradução e análise manuais.
- A geração automática de imagens não foi incluída (o pedido a previa como módulo opcional). O sistema só recomenda recursos encontrados nas fontes e descreve o que deve ser produzido.
