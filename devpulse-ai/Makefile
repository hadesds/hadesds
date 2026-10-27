# Atalhos para o terminal do WSL2. Requer Docker Desktop com integração WSL ativada.
COMPOSE = docker compose

.PHONY: up down restart logs logs-worker ps update build edition collect test test-frontend psql backup shell

up:            ## Constrói (se preciso) e inicia tudo em segundo plano
	$(COMPOSE) up -d --build
down:          ## Para os serviços (os dados ficam no volume)
	$(COMPOSE) down
restart:
	$(COMPOSE) restart api worker
logs:          ## Acompanha os logs de todos os serviços
	$(COMPOSE) logs -f --tail=200
logs-worker:
	$(COMPOSE) logs -f --tail=200 worker
ps:
	$(COMPOSE) ps
update:        ## Atualiza o código (git pull), reconstrói e aplica migrações
	git pull --ff-only && $(COMPOSE) up -d --build
build:
	$(COMPOSE) build
edition:       ## Registra uma edição manual (o worker processa em até 1 min)
	$(COMPOSE) exec worker python -m devpulse.cli edition
collect:       ## Coleta todas as fontes agora
	$(COMPOSE) exec worker python -m devpulse.cli collect --all
test:          ## Testes do backend (unitários + integração em banco devpulse_test temporário)
	$(COMPOSE) run --rm api sh -c 'export TEST_DATABASE_URL="postgresql+psycopg://$$POSTGRES_USER:$$POSTGRES_PASSWORD@db:5432/devpulse_test"; python tests/create_test_db.py && pytest'
test-frontend:
	cd frontend && npm ci && npm test
psql:
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-devpulse} $${POSTGRES_DB:-devpulse}
backup:        ## Gera backup do banco em ./backups
	mkdir -p backups && $(COMPOSE) exec -T db pg_dump -U $${POSTGRES_USER:-devpulse} $${POSTGRES_DB:-devpulse} | gzip > backups/devpulse-$$(date +%F-%H%M).sql.gz
shell:
	$(COMPOSE) exec api bash
