from types import SimpleNamespace

from backend.evaluation.answer_benchmark import TimingLLMClient


def test_timing_llm_client_exposes_delegate_usage():
    usage = object()
    delegate = SimpleNamespace(last_usage=usage)

    assert TimingLLMClient(delegate).last_usage is usage
