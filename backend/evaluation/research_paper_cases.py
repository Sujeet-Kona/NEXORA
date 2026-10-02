"""Research-paper evaluation cases for NEXORA retrieval benchmarks."""

PAPER_CASE_DATA = [
    # Attention Is All You Need
    {
        "question": "What architecture does the Transformer use?",
        "document": "Attention Is All You Need.pdf",
        "anchor": "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
        "expected": ("Transformer", "attention mechanisms"),
    },
    {
        "question": "What does the Transformer dispense with?",
        "document": "Attention Is All You Need.pdf",
        "anchor": "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
        "expected": ("recurrence", "convolutions"),
    },
    {
        "question": "What BLEU score did the Transformer achieve on WMT 2014 English-to-German?",
        "document": "Attention Is All You Need.pdf",
        "anchor": "Our model achieves 28.4 BLEU on the WMT 2014",
        "expected": ("28.4 BLEU",),
    },
    {
        "question": "How long did the Transformer train for on WMT 2014 English-to-French?",
        "document": "Attention Is All You Need.pdf",
        "anchor": "On the WMT 2014 English-to-French translation task, our model establishes a new single-model state-of-the-art BLEU score of 41.8 after training for 3.5 days on eight GPUs, a small fraction of the training costs of the best models from the literature.",
        "expected": ("3.5 days", "eight GPUs"),
    },
    {
        "question": "What BLEU score did the Transformer achieve on WMT 2014 English-to-French?",
        "document": "Attention Is All You Need.pdf",
        "anchor": "On the WMT 2014 English-to-French translation task, our model establishes a new single-model state-of-the-art BLEU score of 41.8 after training for 3.5 days on eight GPUs, a small fraction of the training costs of the best models from the literature.",
        "expected": ("41.8",),
    },

    # LoRA
    {
        "question": "What does LoRA freeze during adaptation?",
        "document": "LORA.pdf",
        "anchor": "which freezes the pretrained model weights",
        "expected": ("pre-trained model weights",),
    },
    {
        "question": "What does LoRA inject into each Transformer layer?",
        "document": "LORA.pdf",
        "anchor": "injects trainable rank decomposition matrices into each layer of the Transformer architecture",
        "expected": ("trainable rank decomposition matrices",),
    },
    {
        "question": "By how much can LoRA reduce trainable parameters for GPT-3 175B?",
        "document": "LORA.pdf",
        "anchor": "reduce the number of trainable parameters by 10,000 times",
        "expected": ("10,000 times",),
    },
    {
        "question": "How much can LoRA reduce GPU memory requirements?",
        "document": "LORA.pdf",
        "anchor": "the GPU memory requirement by 3 times",
        "expected": ("3 times",),
    },
    {
        "question": "Does LoRA add inference latency compared with adapters?",
        "document": "LORA.pdf",
        "anchor": "unlike adapters, no additional inference latency",
        "expected": ("no additional inference latency",),
    },

    # Parameter-Efficient Transfer Learning for NLP
    {
        "question": "Why is full fine-tuning parameter inefficient across many downstream tasks?",
        "document": "PEFT.pdf",
        "anchor": "fine-tuning is parameter inefficient",
        "expected": ("parameter inefficient", "entire new model"),
    },
    {
        "question": "What alternative to full fine-tuning is proposed in the adapter paper?",
        "document": "PEFT.pdf",
        "anchor": "As an alternative, we propose transfer with adapter modules.",
        "expected": ("adapter modules",),
    },
    {
        "question": "What remains fixed when using adapter modules?",
        "document": "PEFT.pdf",
        "anchor": "The parameters of the original network remain fixed, yielding a high degree of parameter sharing.",
        "expected": ("parameters of the original network", "remain fixed"),
    },
    {
        "question": "How many diverse text classification tasks were used to evaluate adapters?",
        "document": "PEFT.pdf",
        "anchor": "26 diverse text classification tasks",
        "expected": ("26",),
    },
    {
        "question": "What percentage of parameters per task did adapters add on GLUE?",
        "document": "PEFT.pdf",
        "anchor": "On GLUE, we attain within 0.4% of the performance of full fine-tuning, adding only 3.6% parameters per task.",
        "expected": ("3.6%",),
    },

    # Retrieval-Augmented Generation
    {
        "question": "Why are pretrained language models limited on knowledge-intensive tasks?",
        "document": "RAG.pdf",
        "anchor": "However, their ability to access and precisely manipulate",
        "expected": ("access and precisely manipulate knowledge",),
    },
    {
        "question": "What two problems remain open around provenance and updating world knowledge?",
        "document": "RAG.pdf",
        "anchor": "Additionally, providing provenance for their decisions and updating their world knowledge remain open research problems.",
        "expected": ("providing provenance", "updating their world knowledge"),
    },
    {
        "question": "What two types of memory do RAG models combine?",
        "document": "RAG.pdf",
        "anchor": "models which combine pre-trained parametric and non-parametric",
        "expected": ("parametric", "non-parametric memory"),
    },
    {
        "question": "What does the non-parametric memory in the RAG models consist of?",
        "document": "RAG.pdf",
        "anchor": "We introduce RAG models where the parametric memory is a pre-trained seq2seq model and the non-parametric memory is a dense vector index of Wikipedia, accessed with a pre-trained neural retriever.",
        "expected": ("dense vector index of Wikipedia",),
    },
    {
        "question": "How did RAG compare with a parametric-only seq2seq baseline for language generation?",
        "document": "RAG.pdf",
        "anchor": "For language generation tasks, we find that RAG models generate more specific, diverse and factual language than a state-of-the-art parametric-only seq2seq baseline.",
        "expected": ("more specific, diverse and factual language",),
    },

    # RoFormer / RoPE
    {
        "question": "What method does RoFormer propose for positional information?",
        "document": "RoPE.pdf",
        "anchor": "Then, we propose a novel method named Rotary Position Embedding(RoPE) to effectively leverage the positional information.",
        "expected": ("Rotary Position Embedding", "RoPE"),
    },
    {
        "question": "How does RoPE encode absolute position?",
        "document": "RoPE.pdf",
        "anchor": "Specifically, the proposed RoPE encodes the absolute position with a rotation matrix and meanwhile incorporates the explicit relative position dependency in self-attention formulation.",
        "expected": ("rotation matrix",),
    },
    {
        "question": "What relative-position property does RoPE incorporate into self-attention?",
        "document": "RoPE.pdf",
        "anchor": "Specifically, the proposed RoPE encodes the absolute position with a rotation matrix and meanwhile incorporates the explicit relative position dependency in self-attention formulation.",
        "expected": ("explicit relative position dependency",),
    },
    {
        "question": "How does inter-token dependency change with increasing relative distance under RoPE?",
        "document": "RoPE.pdf",
        "anchor": "Notably, RoPE enables valuable properties, including the flexibility of sequence length, decaying inter-token dependency with increasing relative distances, and the capability of equipping the linear self-attention with relative position encoding.",
        "expected": ("decaying inter-token dependency",),
    },
    {
        "question": "What kind of datasets were used to evaluate RoFormer?",
        "document": "RoPE.pdf",
        "anchor": "Finally, we evaluate the enhanced transformer with rotary position embedding, also called RoFormer, on various long text classification benchmark datasets.",
        "expected": ("long text classification benchmark datasets",),
    },

    # LLaMA
    {
        "question": "What parameter range does the LLaMA model family cover?",
        "document": "LLAMA.pdf",
        "anchor": "We introduce LLaMA, a collection of foundation language models ranging from 7B to 65B parameters.",
        "expected": ("7B to 65B",),
    },
    {
        "question": "How much training data did LLaMA use?",
        "document": "LLAMA.pdf",
        "anchor": "We train our models on trillions of tokens, and show that it is possible to train state-of-the-art models using publicly available datasets exclusively, without resorting to proprietary and inaccessible datasets.",
        "expected": ("trillions of tokens",),
    },
    {
        "question": "What type of datasets did the LLaMA authors use?",
        "document": "LLAMA.pdf",
        "anchor": "We train our models on trillions of tokens, and show that it is possible to train state-of-the-art models using publicly available datasets exclusively, without resorting to proprietary and inaccessible datasets.",
        "expected": ("publicly available datasets exclusively",),
    },
    {
        "question": "Which LLaMA model was reported to outperform GPT-3 175B on most benchmarks?",
        "document": "LLAMA.pdf",
        "anchor": "LLaMA-13B outperforms GPT-3 (175B) on most benchmarks",
        "expected": ("LLaMA-13B", "GPT-3"),
    },
    {
        "question": "Which models did LLaMA-65B compare competitively with?",
        "document": "LLAMA.pdf",
        "anchor": "is competitive with the best models, Chinchilla-70B and PaLM-540B",
        "expected": ("Chinchilla-70B", "PaLM-540B"),
    },
]

PAPER_NEGATIVE_CASE_DATA = [
    {"question": "What does the LLaMA paper say about quantum computing policy?", "topic": "quantum computing policy"},
    {"question": "What does the LoRA paper specify about cryptocurrency trading?", "topic": "cryptocurrency trading"},
    {"question": "What does the RAG paper say about employee payroll?", "topic": "employee payroll"},
]
