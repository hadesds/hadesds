"""Checagem das afirmações do roteiro contra o texto das fontes coletadas.

Regras:
* Toda afirmação precisa citar uma fonte (S1, S2...) e um trecho literal dela.
* O trecho é procurado no texto coletado; números e versões da afirmação
  precisam aparecer na fonte.
* Números/versões presentes nas falas e ausentes de todas as fontes são
  sinalizados como não sustentados.
Nenhuma etapa considera "verificado" algo que só foi afirmado pelo modelo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from devpulse.content_extraction.extractor import check_link
from devpulse.content_extraction.text import normalize_for_match, tokens
from devpulse.script_generation.schema import Claim, Scene
from devpulse.script_generation.sources import SourceDoc

NUMBER = re.compile(r"(?<![\w.])(v?\d+(?:[.,]\d+)*%?)(?![\w])")


def _norm_number(n: str) -> str:
    n = n.lower().lstrip("v").rstrip("%")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", n):  # 1.000.000 (pt-BR)
        return n.replace(".", "")
    return n.replace(",", ".")


def numbers_in(text: str) -> set[str]:
    return {_norm_number(m) for m in NUMBER.findall(text or "")}


def significant_numbers(text: str) -> set[str]:
    out = set()
    for n in numbers_in(text):
        if "." in n or len(n) >= 2 and not (n.isdigit() and int(n) <= 10):
            out.add(n)
    return out


def _source_numbers(text: str) -> set[str]:
    nums = numbers_in(text)
    nums |= {n.replace(",", "") for n in re.findall(r"\d{1,3}(?:,\d{3})+", text or "")}  # 1,000 (en)
    return nums


def quote_support(quote: str, doc_text: str) -> float:
    q, d = normalize_for_match(quote), normalize_for_match(doc_text)
    if not q:
        return 0.0
    if q in d:
        return 1.0
    qt = [t for t in tokens(quote) if len(t) > 2]
    if not qt:
        return 0.0
    dt = set(tokens(doc_text))
    coverage = sum(t in dt for t in qt) / len(qt)
    grams = {tuple(qt[i : i + 3]) for i in range(len(qt) - 2)}
    dlist = tokens(doc_text)
    dgrams = {tuple(dlist[i : i + 3]) for i in range(len(dlist) - 2)}
    gram_cov = len(grams & dgrams) / len(grams) if grams else coverage
    return round(0.4 * coverage + 0.6 * gram_cov, 3)


@dataclass
class ClaimCheck:
    claim: Claim
    result: str
    evidence_type: str
    source_url: str | None
    notes: str


@dataclass
class CheckReport:
    claims: list[ClaimCheck] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def central_ok(self) -> bool:
        central = [c for c in self.claims if c.claim.is_central]
        return bool(central) and all(c.result == "supported" for c in central)

    @property
    def status(self) -> str:
        all_links_down = bool(self.links) and all(link["accessible"] is False for link in self.links)
        if not self.central_ok or all_links_down:
            return "rejected"
        if self.unsupported_numbers or any(c.result != "supported" for c in self.claims):
            return "verified_with_warnings"
        return "verified"


def check_claim(claim: Claim, docs: dict[str, SourceDoc]) -> ClaimCheck:
    doc = docs.get(claim.source_ref)
    if doc is None:
        return ClaimCheck(claim, "unverifiable", "none", None, f"Fonte {claim.source_ref} inexistente")
    if not claim.quote.strip():
        return ClaimCheck(claim, "unverifiable", doc.evidence_type, doc.url, "Sem trecho de sustentação")
    support = quote_support(claim.quote, doc.text)
    missing = significant_numbers(claim.text) - _source_numbers(doc.text)
    if support >= 0.9 and not missing:
        result, notes = "supported", f"Trecho encontrado na fonte (aderência {support:.0%})"
    elif support >= 0.6:
        result, notes = "partially_supported", f"Trecho só parcialmente encontrado (aderência {support:.0%})"
    else:
        result, notes = "unsupported", f"Trecho não encontrado na fonte (aderência {support:.0%})"
    if missing:
        result = "unsupported" if result != "supported" or claim.is_central else "partially_supported"
        notes += f"; números ausentes da fonte: {', '.join(sorted(missing))}"
    if claim.claim_type in ("forecast", "opinion", "rumor"):
        notes += f"; classificada como {claim.claim_type} — apresentar como tal"
    if doc.evidence_type == "newsletter":
        notes += "; sustentada apenas por newsletter (fonte secundária)"
    return ClaimCheck(claim, result, doc.evidence_type, doc.url, notes)


def check_package(claims: list[Claim], scenes: list[Scene], docs: list[SourceDoc], http: httpx.Client | None) -> CheckReport:
    report = CheckReport()
    by_ref = {d.ref: d for d in docs}
    report.claims = [check_claim(c, by_ref) for c in claims]
    all_numbers: set[str] = set()
    for d in docs:
        all_numbers |= _source_numbers(d.text) | _source_numbers(d.title)
    spoken = set()
    for s in scenes:
        spoken |= significant_numbers(f"{s.speech} {s.overlay_text}")
    report.unsupported_numbers = sorted(spoken - all_numbers)
    for d in docs:
        if http is None:
            report.links.append({"url": d.url, "accessible": None, "status": None})
            continue
        ok, status, final = check_link(http, d.url)
        report.links.append({"url": d.url, "accessible": ok, "status": status, "final_url": final})
    if not any(c.claim.is_central for c in report.claims):
        report.problems.append("Nenhuma afirmação central declarada")
    for c in report.claims:
        if c.result != "supported":
            report.problems.append(f"Afirmação '{c.claim.text[:120]}' → {c.result}: {c.notes}")
    for n in report.unsupported_numbers:
        report.problems.append(f"Número/versão '{n}' aparece nas falas mas não nas fontes")
    for link in report.links:
        if link["accessible"] is False:
            report.problems.append(f"Fonte inacessível agora: {link['url']} (HTTP {link['status']})")
    return report
