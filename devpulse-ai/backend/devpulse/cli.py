"""Linha de comando: ``python -m devpulse.cli <comando>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from devpulse.config import get_settings
from devpulse.db import session_scope
from devpulse.observability.logging import configure_logging


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    p = argparse.ArgumentParser(prog="devpulse")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Aplica as migrações do banco")
    sub.add_parser("seed", help="Carrega fontes de config/sources.yaml")
    sub.add_parser("init", help="migrate + seed")
    c = sub.add_parser("collect", help="Coleta as fontes agora")
    c.add_argument("--all", action="store_true", help="Ignora o intervalo de cada fonte")
    c.add_argument("--source", help="slug de uma fonte")
    e = sub.add_parser("edition", help="Registra uma edição manual (processada pelo worker) ou executa já com --now")
    e.add_argument("--now", action="store_true", help="Processa imediatamente neste processo")
    e.add_argument("--no-collect", action="store_true")
    e.add_argument("--no-deliver", action="store_true", help="Gera roteiros sem criar entregas")
    sub.add_parser("worker", help="Inicia o agendador")
    sub.add_parser("recover", help="Executa uma rodada de recuperação (tick)")
    sub.add_parser("sources", help="Lista fontes e o último status")
    x = sub.add_parser("export", help="Exporta um roteiro em Markdown")
    x.add_argument("script_id", type=int)
    args = p.parse_args(argv)

    if args.cmd in ("migrate", "init"):
        _migrate()
        print("Migrações aplicadas.")
    if args.cmd in ("seed", "init"):
        from devpulse.seed import seed_sources

        with session_scope() as s:
            print(json.dumps(seed_sources(s, get_settings().sources_file)))
    if args.cmd == "collect":
        from sqlalchemy import select

        from devpulse.models import Source
        from devpulse.news_ingestion.service import collect_all, collect_source

        with session_scope() as s:
            if args.source:
                src = s.scalar(select(Source).where(Source.slug == args.source))
                if not src:
                    print("Fonte não encontrada", file=sys.stderr)
                    return 1
                r = collect_source(s, src)
                print(json.dumps({"status": r.status, "found": r.items_found, "new": r.items_new, "error": r.error}))
            else:
                print(json.dumps(collect_all(s, force=args.all)))
    if args.cmd == "edition":
        from devpulse.scheduler.jobs import process_run, request_manual
        from devpulse.scheduler.pipeline import run_edition
        from devpulse.scheduler.runs import claim_run, finish

        with session_scope() as s:
            run = request_manual(s, "edition")
            if not args.now:
                print(f"Edição registrada ({run.run_key}); o worker a processa em até 1 minuto.")
            elif args.no_deliver or args.no_collect:
                claim_run(s, run)
                stats = run_edition(s, run, collect=not args.no_collect, deliver=not args.no_deliver)
                finish(s, run, "completed")
                print(json.dumps(stats, ensure_ascii=False, default=str))
            else:
                process_run(s, run)
                s.refresh(run)
                print(json.dumps({"status": run.status, "stats": run.stats, "error": run.error}, ensure_ascii=False, default=str))
    if args.cmd == "worker":
        from devpulse.scheduler.worker import main as worker_main

        worker_main()
    if args.cmd == "recover":
        from devpulse.scheduler.jobs import tick

        tick()
        print("Rodada de recuperação concluída.")
    if args.cmd == "sources":
        from sqlalchemy import select

        from devpulse.models import Source

        with session_scope() as s:
            for src in s.scalars(select(Source).order_by(Source.priority_tier)):
                state = "ativa" if src.enabled else "inativa"
                print(f"{src.slug:32} {src.connector_type:17} {state:8} último erro: {src.last_error or '-'}")
    if args.cmd == "export":
        from devpulse.models import Script

        with session_scope() as s:
            sc = s.get(Script, args.script_id)
            if not sc:
                print("Roteiro não encontrado", file=sys.stderr)
                return 1
            print(sc.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
