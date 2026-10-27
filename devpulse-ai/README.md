# DevPulse AI

Redação pessoal de tecnologia que roda no seu computador. O DevPulse monitora newsletters, blogs oficiais, changelogs e APIs públicas, verifica as fontes, escolhe **até três** boas histórias por dia e entrega roteiros completos para Instagram Reels por **e-mail** e **WhatsApp**. Ele não publica nada no Instagram: a gravação e a publicação continuam com você.

- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, APScheduler (job store no PostgreSQL)
- Painel: React 18 + TypeScript (Vite), servido pelo próprio backend
- Banco: PostgreSQL 16 em volume Docker
- Orquestração: Docker Compose, usando o Docker Desktop que você já tem (sem um segundo Docker Engine no WSL2)

> Situação das integrações: veja [docs/relatorio-de-testes.md](docs/relatorio-de-testes.md). Lá está o que foi testado de verdade, o que foi testado com simulação e o que ainda depende das suas credenciais.

---

## 1. Como funciona

```
fontes (RSS/Atom · APIs · releases GitHub · páginas · newsletter por e-mail)
   │  coleta incremental (a cada 60 min)
   ▼
ingestão ─► deduplicação (URL normalizada, id da fonte, título, termos-chave) ─► agrupamento por acontecimento
   │
   ▼  edição das 08:00 (America/Fortaleza)
extração do conteúdo acessível (respeita robots.txt e paywalls)
   ▼
pontuação editorial 0–100 ─► elegibilidade (atualidade, fonte primária ou 2 fontes independentes, retenção de temas)
   ▼
seleção (até 3, com diversidade de categorias) ─► roteiro (IA ou roteiro-base extrativo)
   ▼
checagem automática (trechos literais, números/versões, links) ─► reprovado? tenta a próxima notícia
   ▼
entregas idempotentes: e-mail (HTML + texto) e WhatsApp (template oficial), com estados separados
```

Os módulos ficam em `backend/devpulse/`: `source_connectors`, `news_ingestion`, `content_extraction`, `deduplication`, `editorial_scoring`, `fact_checking`, `script_generation`, `media_research`, `email_delivery`, `whatsapp_delivery`, `scheduler`, `admin_dashboard` e `observability`. A arquitetura está descrita em [docs/arquitetura.md](docs/arquitetura.md).

**Sem IA configurada** (`LLM_PROVIDER=none`), o sistema continua funcionando. Ele gera um **roteiro-base extrativo** montado só com frases literais da fonte, no idioma original e marcado como tal. A análise de impacto fica para você escrever. Assim o sistema nunca inventa conteúdo para preencher a edição.

---

## 2. Instalação no Windows + WSL2 (Arch Linux) com Docker Desktop

### 2.1 Pré-requisitos (uma vez)

1. **Docker Desktop** instalado no Windows, com backend WSL2.
2. Em *Docker Desktop → Settings → Resources → WSL integration*, ative a integração para a sua distribuição Arch. Isso disponibiliza `docker` e `docker compose` dentro do WSL **usando o daemon do Docker Desktop**. Não instale `docker`/`containerd` pelo `pacman`.
3. No Arch (WSL), instale apenas as ferramentas de linha de comando:
   ```bash
   sudo pacman -S --needed git make python
   docker version          # deve mostrar "Server: Docker Desktop"
   docker compose version
   ```
   Se `docker version` não mostrar o servidor, reinicie o Docker Desktop e confira a integração WSL. Não altere o `daemon.json` nem outras configurações globais.
4. Clone o repositório **dentro do sistema de arquivos do WSL** (ex.: `~/projetos`), não em `/mnt/c/...`. Assim a construção das imagens fica bem mais rápida.

### 2.2 Configuração

```bash
cd ~/projetos/hadesds/devpulse-ai
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"      # cole no .env
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"  # cole no .env
```

Edite o `.env` e defina pelo menos `SECRET_KEY`, `ADMIN_PASSWORD` (10+ caracteres) e `POSTGRES_PASSWORD`. Os canais de entrega começam **desativados** e são ligados à medida que você configura cada um:

- e-mail de saída e caixa de newsletters: [docs/configuracao-email.md](docs/configuracao-email.md)
- WhatsApp Business Platform: [docs/configuracao-whatsapp.md](docs/configuracao-whatsapp.md)
- IA: `LLM_PROVIDER=anthropic` e `LLM_API_KEY=...` (custos em [docs/custos-e-limites.md](docs/custos-e-limites.md))

### 2.3 Comandos do dia a dia

| Ação | Comando |
|---|---|
| Iniciar (constrói na primeira vez) | `make up` ou `docker compose up -d --build` |
| Parar | `make down` ou `docker compose down` |
| Ver logs (todos) | `make logs` ou `docker compose logs -f --tail=200` |
| Logs só do agendador | `make logs-worker` |
| Situação dos serviços | `make ps` |
| Atualizar (git pull + rebuild + migrações) | `make update` |
| Gerar uma edição agora | `make edition` (ou o botão no painel) |
| Coletar todas as fontes agora | `make collect` |
| Testes do backend | `make test` |
| Testes do painel | `make test-frontend` |
| Backup do banco | `make backup` (gera `backups/*.sql.gz`) |
| Console do banco | `make psql` |

Sem `make`, use os comandos `docker compose` correspondentes do `Makefile`.

Painel: **http://localhost:8080**, com o usuário `admin` e a senha definida em `ADMIN_PASSWORD`. A porta fica presa a `127.0.0.1` e não é exposta à rede local nem à internet. No Windows, o `localhost` do navegador alcança o WSL2 normalmente.

`docker compose down` mantém os dados no volume `devpulse_pgdata`. Só `docker compose down -v` apaga o banco.

### 2.4 Serviços do Compose

| Serviço | Papel |
|---|---|
| `db` | PostgreSQL 16 (volume `pgdata`; porta 5433 só em 127.0.0.1, para depuração) |
| `migrate` | Roda uma vez a cada `up`: aplica as migrações Alembic e cadastra fontes novas de `config/sources.yaml` |
| `api` | FastAPI + painel React em `127.0.0.1:8080` |
| `worker` | APScheduler. Faz a coleta periódica, a edição das 08:00, a recuperação e as entregas. Um advisory lock do PostgreSQL impede que dois workers rodem ao mesmo tempo |

---

## 3. Agenda, limites e recuperação

- Edição principal às **08:00** em `America/Fortaleza` (São Luís–MA). A edição complementar é opcional (`EDITION_SECONDARY_TIME`).
- **Até 3 roteiros por dia**, somando todas as execuções do dia (principal, complementar e manual). O mesmo roteiro enviado por e-mail e por WhatsApp conta uma vez só.
- **Computador desligado às 08:00:** quando o worker volta, ele roda a edição do dia se ainda estiver antes de `EDITION_CATCHUP_UNTIL` (padrão 14:00). Depois desse horário, a edição fica registrada como "ignorada" e não é enviada com atraso. Edições de dias anteriores nunca são disparadas.
- **Reinício no meio de uma edição:** a execução é retomada da etapa em que parou. Roteiros já gerados não são refeitos (há restrição única por dia + agrupamento), e entregas já aceitas não são reenviadas (há chave de idempotência por execução + canal + destinatário).
- **Envio interrompido** (container caiu durante o envio): a entrega vai para "revisar". Não há reenvio automático, porque não dá para saber se o provedor recebeu a mensagem. O reenvio é manual, pelo painel.
- Retentativas com intervalo crescente (2, 10, 30, 90 e 240 min) só para falhas temporárias. Erros de autenticação não são repetidos.

---

## 4. Fontes

As fontes iniciais estão em [`config/sources.yaml`](config/sources.yaml). A primeira é a **TechDrops**, cujo remetente é `tech@newsletter.thedrops.com.br`. Ela é lida da **sua** caixa de entrada, que é configurada separadamente no `.env`.

Há três jeitos de adicionar fontes, nenhum deles exige mudar o núcleo:

1. **Pelo painel** → Fontes → "Adicionar fonte" (RSS/Atom, API JSON, releases do GitHub, página de listagem, newsletter).
2. **Pelo YAML**: acrescente um bloco em `config/sources.yaml` e rode `docker compose up -d` (o serviço `migrate` cadastra só as novas).
3. **Novo tipo de conector**: crie um módulo Python com uma classe que herda de `SourceConnector`, decore com `@register("meu_tipo")` e liste o módulo em `PLUGIN_MODULES`. Detalhes em [docs/arquitetura.md](docs/arquitetura.md#conectores).

O nível da fonte (1 oficial … 5 agregador) pesa na confiabilidade. Duas matérias que reproduzem o mesmo comunicado não contam como confirmações independentes.

---

## 5. Desenvolvimento sem Docker (opcional)

```bash
# backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://devpulse:SENHA@localhost:5433/devpulse   # Postgres do compose
export SOURCES_FILE=../config/sources.yaml SECRET_KEY=... ADMIN_PASSWORD=... FRONTEND_DIST=../frontend/dist
python -m devpulse.cli init
uvicorn devpulse.main:app --reload --port 8080      # API + painel compilado
python -m devpulse.cli worker                       # em outro terminal

# painel com recarga automática (proxy para a API em 8080)
cd frontend && npm ci && npm run dev                # http://127.0.0.1:5173
```

CLI: `python -m devpulse.cli {init|migrate|seed|collect [--all|--source SLUG]|edition [--now] [--no-collect] [--no-deliver]|worker|recover|sources|export ID}`.

---

## 6. Documentação

- [Plano técnico e arquitetura](docs/arquitetura.md)
- [Configuração de e-mail (saída e caixa de newsletters)](docs/configuracao-email.md)
- [Configuração do WhatsApp Business](docs/configuracao-whatsapp.md)
- [Custos, limites e dependências externas](docs/custos-e-limites.md)
- [Relatório de testes e pendências](docs/relatorio-de-testes.md)
- Exemplos reais: [roteiro](docs/examples/roteiro-exemplo-anthropic-s1.md) · [e-mail](docs/examples/email-exemplo.html) · [WhatsApp](docs/examples/whatsapp-exemplo.txt)
