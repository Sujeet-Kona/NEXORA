from backend.services.llm.base import LLMUsage, llm_usage_context


def test_llm_usage_context_isolated_between_contexts():
    first = llm_usage_context.copy_context()
    second = llm_usage_context.copy_context()

    first.run(llm_usage_context.set, LLMUsage(input_tokens=10, output_tokens=2, total_tokens=12))
    second.run(llm_usage_context.set, LLMUsage(input_tokens=20, output_tokens=4, total_tokens=24))

    assert first.get(llm_usage_context) == LLMUsage(input_tokens=10, output_tokens=2, total_tokens=12)
    assert second.get(llm_usage_context) == LLMUsage(input_tokens=20, output_tokens=4, total_tokens=24)
    assert llm_usage_context.get() is None
