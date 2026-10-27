from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from devpulse.script_generation.render import to_markdown
from devpulse.script_generation.schema import ScriptPackage

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
FORMAT = {"noticia_rapida": "Notícia rápida", "explicacao": "Explicação", "tutorial": "Tutorial",
          "demonstracao": "Demonstração", "analise": "Análise"}


def render_edition(*, edition_label: str, packages: list[ScriptPackage], summary: str, dashboard_url: str,
                   empty_reasons: list[str]) -> tuple[str, str, str]:
    """Retorna (assunto, html, texto)."""
    n = len(packages)
    subject = (
        f"DevPulse AI — {edition_label}: {n} roteiro{'s' if n != 1 else ''}"
        if n else f"DevPulse AI — {edition_label}: nenhuma notícia suficientemente verificada"
    )
    html = _env.get_template("edition.html").render(
        edition_label=edition_label, packages=packages, summary=summary, dashboard_url=dashboard_url,
        empty_reasons=empty_reasons, fmt=FORMAT,
    )
    parts = [subject, "=" * len(subject), "", summary, ""]
    if not packages:
        parts += ["Nenhuma notícia atendeu aos critérios mínimos de verificação hoje.", ""]
        parts += [f"- {r}" for r in empty_reasons[:10]]
    for i, p in enumerate(packages, start=1):
        parts += ["", f"########## ROTEIRO {i} ##########", "", to_markdown(p)]
    parts += ["", f"Painel local (acessível apenas no seu computador): {dashboard_url}"]
    return subject, html, "\n".join(parts)
