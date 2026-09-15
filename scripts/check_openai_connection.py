from openai import OpenAI

from backend.core.config import settings


def main() -> None:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    if not settings.openai_model:
        raise RuntimeError("OPENAI_MODEL is not configured")

    client = OpenAI(
        api_key=settings.openai_api_key,
    )

    response = client.responses.create(
        model=settings.openai_model,
        input="Reply with exactly: Nexora LLM connection OK",
    )

    print(response.output_text)


if __name__ == "__main__":
    main()
