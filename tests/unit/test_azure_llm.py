"""Azure OpenAI provider (GPT-4.1 deployment, OpenAI v1 Responses API): configuration, request shape, failure handling.

No network: the OpenAI client is replaced by fakes. A live call is made only by the evaluation scripts.
"""
from types import SimpleNamespace

import pytest

from backend.config import Settings, settings
from backend.services import llm, rag

KEY = "FakeAzureKey-0123456789abcdefABCDEF"
ENDPOINT = "https://example-resource.services.ai.azure.com/openai/v1"
PASSAGES = [{"source": "handbook.pdf", "section": "3. Payroll", "page": 2,
             "text": "Salary is credited on the last working day of every month."}]


@pytest.fixture(autouse=True)
def azure_settings(monkeypatch):
    monkeypatch.setattr(settings, "azure_openai_endpoint", ENDPOINT)
    monkeypatch.setattr(settings, "azure_openai_deployment", "gpt-4.1")
    monkeypatch.setattr(settings, "azure_openai_api_key", KEY)


class FakeOpenAI:
    """Records constructor and request arguments; returns a configurable Responses API result."""

    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.requests = []
        self.result = SimpleNamespace(status="completed", output_text="Salary is credited ... [Handbook 3]")
        self.error = None
        self.responses = SimpleNamespace(create=self._create)
        FakeOpenAI.instances.append(self)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def fake(monkeypatch):
    FakeOpenAI.instances = []
    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    return FakeOpenAI


# ---------------------------------------------------------------- endpoint normalisation
@pytest.mark.parametrize("endpoint", [
    "https://example-resource.services.ai.azure.com/openai/v1",
    "https://example-resource.services.ai.azure.com/openai/v1/",
    "https://example-resource.services.ai.azure.com",
    "https://example-resource.services.ai.azure.com/",
    "https://example-resource.services.ai.azure.com/openai",
    "  https://example-resource.services.ai.azure.com/openai/v1  ",
])
def test_endpoint_is_normalised_to_the_v1_base_url(endpoint):
    assert llm.normalize_base_url(endpoint) == "https://example-resource.services.ai.azure.com/openai/v1/"


@pytest.mark.parametrize("endpoint", [
    "", "http://x.services.ai.azure.com/openai/v1", "https://user:pw@x.services.ai.azure.com/openai/v1",
    "https://x.services.ai.azure.com/openai/v1?api-version=2024-10-21",
    "https://x.openai.azure.com/openai/deployments/gpt-4.1/chat/completions", "x.services.ai.azure.com",
])
def test_unsafe_or_unexpected_endpoints_are_rejected(endpoint):
    with pytest.raises(ValueError):
        llm.normalize_base_url(endpoint)


# ---------------------------------------------------------------- client and request shape
def test_client_uses_normalised_url_key_timeout_and_retries(fake):
    llm.generate_answer("When is salary credited?", PASSAGES)
    (client,) = fake.instances
    assert client.kwargs == {"api_key": KEY, "base_url": ENDPOINT + "/", "timeout": settings.llm_timeout_seconds,
                             "max_retries": settings.llm_max_retries}


def test_request_uses_responses_api_with_deployment_and_store_false(fake):
    answer = llm.generate_answer("When is salary credited?", PASSAGES)
    (request,) = fake.instances[0].requests
    assert answer == "Salary is credited ... [Handbook 3]"
    assert request["model"] == "gpt-4.1" and request["store"] is False
    assert request["instructions"] == llm.SYSTEM_PROMPT and request["temperature"] == 0
    assert request["max_output_tokens"] == settings.llm_max_output_tokens
    (message,) = request["input"]
    assert message["role"] == "user" and message["content"].startswith("<untrusted_context>")
    assert "[1] (handbook.pdf - 3. Payroll)" in message["content"]
    assert message["content"].endswith("Question: When is salary credited?")
    assert KEY not in str(request)


@pytest.mark.parametrize("missing", ["azure_openai_endpoint", "azure_openai_deployment", "azure_openai_api_key"])
def test_missing_configuration_fails_closed_without_a_request(fake, monkeypatch, missing):
    monkeypatch.setattr(settings, missing, "  ")
    with pytest.raises(llm.LLMUnavailable, match="not configured"):
        llm.generate_answer("q", PASSAGES)
    assert fake.instances == []


def test_invalid_endpoint_fails_closed_without_a_request(fake, monkeypatch):
    monkeypatch.setattr(settings, "azure_openai_endpoint", "http://insecure.example/openai/v1")
    with pytest.raises(llm.LLMUnavailable, match="endpoint is invalid"):
        llm.generate_answer("q", PASSAGES)
    assert fake.instances == []


# ---------------------------------------------------------------- failures
class ProviderError(Exception):
    def __init__(self, message, status_code=None, code=None):
        super().__init__(message)
        self.status_code, self.code = status_code, code


def _failing(fake, monkeypatch, error):
    original = FakeOpenAI.__init__

    def init(self, **kwargs):
        original(self, **kwargs)
        self.error = error

    monkeypatch.setattr(FakeOpenAI, "__init__", init)


def test_provider_errors_become_llm_unavailable_without_secrets(fake, monkeypatch):
    _failing(fake, monkeypatch, ProviderError(f"401 invalid key {KEY} at {ENDPOINT}", status_code=401))
    with pytest.raises(llm.LLMUnavailable) as exc:
        llm.generate_answer("q", PASSAGES)
    text = str(exc.value)
    assert "ProviderError" in text and "HTTP 401" in text
    assert KEY not in text and "services.ai.azure.com" not in text
    assert isinstance(exc.value.__cause__, ProviderError)


def test_prompt_blocked_by_content_filter_returns_not_found(fake, monkeypatch):
    _failing(fake, monkeypatch, ProviderError("filtered", status_code=400, code="content_filter"))
    assert llm.generate_answer("q", PASSAGES) == llm.NOT_FOUND


def test_incomplete_response_is_never_returned(fake, monkeypatch):
    original = FakeOpenAI.__init__

    def init(self, **kwargs):
        original(self, **kwargs)
        self.result = SimpleNamespace(status="incomplete", output_text="Partial answer [Handbook 3]",
                                      incomplete_details=SimpleNamespace(reason="content_filter"))

    monkeypatch.setattr(FakeOpenAI, "__init__", init)
    assert llm.generate_answer("q", PASSAGES) == ""


def test_rag_pipeline_turns_filtered_or_incomplete_output_into_the_fallback(monkeypatch):
    hits = [dict(PASSAGES[0], score=0.9)]
    monkeypatch.setattr(rag.retriever, "search", lambda q, k=None: hits)
    monkeypatch.setattr(rag.guardrails, "retrieval_gate", lambda q, h: (True, "ok"))
    for raw in ("", llm.NOT_FOUND):
        monkeypatch.setattr(llm, "generate_answer", lambda q, p, raw=raw: raw)
        result = rag.answer_policy("When is salary credited?")
        assert result["answer"] == rag.FALLBACK and result["found"] is False and result["sources"] == []


# ---------------------------------------------------------------- settings
def test_settings_read_azure_variables_and_the_base_url_alias(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://alias.services.ai.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    loaded = Settings(_env_file=None)
    assert loaded.azure_openai_endpoint == "https://alias.services.ai.azure.com/openai/v1"
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://primary.services.ai.azure.com")
    assert Settings(_env_file=None).azure_openai_endpoint == "https://primary.services.ai.azure.com"


def test_groq_is_no_longer_configurable():
    assert not any(name.startswith("groq") or name == "model_name" for name in Settings.model_fields)
    assert llm.PROVIDER == "Azure OpenAI"
