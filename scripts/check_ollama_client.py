from backend.services.llm.ollama_client import OllamaLLMClient


def main() -> None:
    client = OllamaLLMClient()

    answer = client.generate(
        system_prompt=(
            "You are a helpful assistant. "
            "Reply briefly."
        ),
        user_prompt=(
            "Reply with exactly: Nexora provider integration OK"
        ),
    )

    print(answer)


if __name__ == "__main__":
    main()
