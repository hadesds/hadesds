from __future__ import annotations

import json

from devpulse.media_research.research import AssetCandidate
from devpulse.script_generation.sources import SourceDoc

SYSTEM = """Você é roteirista e editor de um canal brasileiro de tecnologia no Instagram Reels.
Público: estudantes, programadores e profissionais de tecnologia.

Regras inegociáveis:
1. Use SOMENTE as fontes fornecidas (S1, S2...). Não use memória para fatos atuais. Não invente nomes,
   datas, números, versões, recursos, citações, resultados de testes nem links.
2. Cada afirmação factual relevante deve aparecer em "claims" com source_ref e um trecho LITERAL copiado
   da fonte (no idioma original) em "quote". Marque is_central=true nas 1–3 afirmações que sustentam o vídeo.
3. Diferencie fato, opinião, previsão e rumor (claim_type). Previsões e opiniões precisam ser ditas como tais
   na fala ("a empresa afirma que...", "a expectativa é...").
4. Só use números e versões que estão nas fontes. Se algo estiver incompleto, diga na fala e liste em "uncertainties".
5. Não apresente nenhuma demonstração como testada: o sistema não executou testes. Use demo_status
   "nao_executada" e explique em demo_note o que o apresentador precisa reproduzir antes de gravar,
   ou "sem_demonstracao" quando não houver demonstração.
6. Escreva em português brasileiro natural, como uma pessoa explicando uma descoberta interessante, com ritmo
   de Reels. Evite frases de efeito sem base ("isso muda tudo", "revolucionário").
7. Texto original: não copie parágrafos das fontes na fala; resuma e explique com suas palavras.
8. Duração entre 30 e 90 segundos conforme a complexidade. Cenas contínuas, começando em 0, sem lacunas.
   Estrutura sugerida (adapte quando fizer sentido): gancho, contexto, novidade, demonstração, impacto, encerramento.
9. Recursos visuais: em scene_visuals (scene_index começa em 1, na ordem das cenas) use apenas os IDs de recursos fornecidos (A1, A2...) ou "PRODUZIR"
   com descrição precisa do que criar. Não escreva URLs em nenhum campo, exceto pages_to_open, que só pode
   conter URLs das fontes ou dos recursos fornecidos.
10. Hashtags relevantes e sem exagero (5 a 10). Não prometa nada que as fontes não sustentam."""


def user_prompt(*, today: str, category: str, docs: list[SourceDoc], assets: list[AssetCandidate], newsletter_note: str) -> str:
    sources = [
        {
            "ref": d.ref,
            "titulo": d.title,
            "url": d.url,
            "publicador": d.publisher,
            "tipo_de_evidencia": d.evidence_type,
            "publicado_em": d.published_at,
            "texto": d.text,
        }
        for d in docs
    ]
    visuals = [
        {"id": a.ref, "tipo": a.kind, "descricao": a.description, "url": a.url, "licenca": a.license_info}
        for a in assets
    ]
    return (
        f"Data de hoje: {today}. Categoria editorial: {category}.\n{newsletter_note}\n"
        "Produza o pacote editorial completo para um Reels sobre o acontecimento descrito nas fontes abaixo.\n\n"
        f"FONTES:\n{json.dumps(sources, ensure_ascii=False, indent=1)}\n\n"
        f"RECURSOS VISUAIS DISPONÍVEIS:\n{json.dumps(visuals, ensure_ascii=False, indent=1)}"
    )


def revision_prompt(original_user: str, draft: dict, problems: list[str]) -> str:
    return (
        original_user
        + "\n\nUm rascunho anterior foi reprovado na checagem automática pelos motivos abaixo. "
        "Reescreva o pacote completo removendo ou reformulando com incerteza explícita tudo o que não está nas "
        "fontes, e corrija os trechos 'quote' para que sejam cópias literais das fontes.\n"
        f"PROBLEMAS:\n- " + "\n- ".join(problems[:30])
        + f"\n\nRASCUNHO REPROVADO:\n{json.dumps(draft, ensure_ascii=False)[:20000]}"
    )


SCORING_SYSTEM = """Você avalia notícias de tecnologia para um canal de Reels voltado a desenvolvedores brasileiros.
Use apenas o título e o resumo fornecidos. Dê notas de 0 a 100 e uma justificativa curta em português.
Não premie polêmica por si só."""
