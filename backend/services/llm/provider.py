from backend.core.config import (
    SUPPORTED_LLM_PROVIDERS,
    Settings,
    settings,
)
from backend.core.exceptions import LLMConfigurationError
from backend.services.llm.base import LLMClient
from backend.services.llm.ollama_client import OllamaLLMClient
from backend.services.llm.openai_client import (
    OpenAICompatibleLLMClient,
)


def build_llm_client(config: Settings = settings) -> LLMClient:
    provider = (config.llm_provider or "").strip().lower()

    if provider == "ollama":
        return OllamaLLMClient()

    if provider == "openai":
        return OpenAICompatibleLLMClient()

    raise LLMConfigurationError(
        "Unsupported LLM_PROVIDER "
        f"'{config.llm_provider}'. Expected one of "
        f"{', '.join(SUPPORTED_LLM_PROVIDERS)}."
    )
