from devpulse.content_extraction.text import detect_language, sentences
from devpulse.deduplication.normalize import normalize_url, title_fingerprint
from devpulse.deduplication.similarity import content_similarity, title_similarity
from devpulse.editorial_scoring.categories import classify, content_type


def test_normalize_url_removes_tracking_and_www():
    a = normalize_url("https://www.Example.com/post/?utm_source=x&b=2&a=1&fbclid=zz#frag")
    b = normalize_url("http://example.com/post?a=1&b=2")
    assert a == b == "https://example.com/post?a=1&b=2"


def test_title_fingerprint_ignores_order_and_stopwords():
    assert title_fingerprint("OpenAI lança novo modelo GPT") == title_fingerprint("Novo modelo GPT: OpenAI lança")


def test_same_event_titles_are_similar():
    s = title_similarity("GitHub Copilot ganha agentes que abrem pull requests", "Copilot do GitHub agora tem agentes para pull requests")
    assert s >= 0.55


def test_different_versions_are_different_events():
    assert title_similarity("Node.js 26.11.0 (Current)", "Node.js 26.11.1 (Current)") == 0.0


def test_unrelated_titles_are_not_similar():
    assert title_similarity("Rust 1.90 released", "Kubernetes adds sidecar containers") < 0.3


def test_content_similarity_detects_republished_press_release():
    text = " ".join(f"word{i} alpha beta gamma delta" for i in range(60))
    assert content_similarity(text, text + " extra trailing sentence") > 0.9


def test_sentences_keep_abbreviations():
    out = sentences("Filed with the U.S. Securities and Exchange Commission today. Another sentence follows here.")
    assert out[0].startswith("Filed with the U.S. Securities")
    assert len(out) == 2


def test_language_detection():
    assert detect_language("O novo recurso da linguagem que os desenvolvedores pediram está disponível para todos") == "pt"
    assert detect_language("The new feature that developers asked for is now available for everyone in the release") == "en"


def test_classify_categories():
    assert classify("Critical CVE-2026-1234 vulnerability exploited in the wild")[0] == "seguranca"
    assert classify("Anthropic releases new Claude model for agents")[0] == "ia"
    assert classify("Kubernetes 1.36 improves cloud autoscaling")[0] == "infraestrutura"
    assert classify("Startup raises Series B funding to hire developers")[0] == "mercado"
    assert classify("TypeScript 6.0 adds new compiler flags")[0] == "desenvolvimento"


def test_content_type_detects_rumor_and_opinion():
    assert content_type("Apple reportedly working on new chip") == "rumor"
    assert content_type("Why I stopped using microservices") == "opinion"
    assert content_type("Go 1.26 released") == "fact"
