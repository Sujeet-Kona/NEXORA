"""Additional grounded evaluation cases for the expanded NEXORA benchmark.

Every case reuses an existing corpus anchor. This keeps benchmark expansion
honest: adding a question never adds an unsupported expected answer.
"""

EXPANDED_CASE_DATA = [
    # Exact / keyword / paraphrase coverage across policy documents.
    {"category": "exact_lookup", "question": "What is the annual leave allowance?", "document": "leave_policy.docx", "anchor": "Employees receive 20 days of annual leave per year.", "expected": ("20 days", "twenty days")},
    {"category": "paraphrase", "question": "How much sick leave is available to an employee in a year?", "document": "leave_policy.docx", "anchor": "Employees receive 10 days of sick leave per year.", "expected": ("10 days", "ten days")},
    {"category": "keyword_heavy", "question": "leave manager approval >3 working days requirement", "document": "leave_policy.docx", "anchor": "Leave requests longer than three working days require manager approval.", "expected": ("three working days", "3 working days")},
    {"category": "semantic", "question": "After which employment milestone can someone work remotely?", "document": "remote_work_policy.docx", "anchor": "Employees who have completed probation may request remote work.", "expected": ("completed probation", "probation")},
    {"category": "identifier", "question": "What authentication acronym is required for supported company systems?", "document": "information_security_policy.docx", "anchor": "All employees must use multi-factor authentication for supported company systems.", "expected": ("multi-factor authentication", "multifactor authentication", "mfa")},
    {"category": "paraphrase", "question": "Can confidential company data be sent externally without approval?", "document": "information_security_policy.docx", "anchor": "Confidential information must not be shared outside the company without authorization.", "expected": ("must not be shared", "not be shared without authorization", "cannot be shared")},
    {"category": "exact_lookup", "question": "What is the minimum required password length?", "document": "password_authentication_policy.docx", "anchor": "Passwords must contain at least 12 characters.", "expected": ("12 characters", "twelve characters")},
    {"category": "keyword_heavy", "question": "password rotation interval 90 days", "document": "password_authentication_policy.docx", "anchor": "Passwords must be changed every 90 days.", "expected": ("90 days", "ninety days")},
    {"category": "semantic", "question": "How many old passwords are blocked from reuse?", "document": "password_authentication_policy.docx", "anchor": "Employees may not reuse their previous five passwords.", "expected": ("five passwords", "5 passwords", "previous five")},
    {"category": "exact_lookup", "question": "What is the daily cap for eligible meal expenses?", "document": "expense_policy.docx", "anchor": "Employees may claim up to Rs. 800 per day for eligible meals incurred during approved business activity.", "expected": ("800",)},
    {"category": "keyword_heavy", "question": "expense receipt threshold Rs 500 itemized", "document": "expense_policy.docx", "anchor": "Expenses above Rs. 500 require an itemized receipt.", "expected": ("500",)},
    {"category": "paraphrase", "question": "What is the deadline for submitting an expense report?", "document": "expense_policy.docx", "anchor": "Expense reports must be submitted within 30 days.", "expected": ("30 days", "thirty days")},
    {"category": "semantic", "question": "How many days make up the normal work week?", "document": "attendance_policy.docx", "anchor": "The standard work week consists of five working days.", "expected": ("five working days", "5 working days", "five days")},
    {"category": "keyword_heavy", "question": "late arrival manager notification 30 minutes", "document": "attendance_policy.docx", "anchor": "Employees arriving more than 30 minutes late must inform their manager.", "expected": ("30 minutes", "thirty minutes")},
    {"category": "paraphrase", "question": "Where do employees log their attendance?", "document": "attendance_policy.docx", "anchor": "Employees must record attendance through the company system.", "expected": ("company system",)},
    {"category": "exact_lookup", "question": "Which cabin class is normally booked for domestic business travel?", "document": "travel_policy.docx", "anchor": "Domestic business travel is normally booked in economy class.", "expected": ("economy",)},
    {"category": "keyword_heavy", "question": "hotel reimbursement maximum per night 5000", "document": "travel_policy.docx", "anchor": "Employees may claim up to Rs. 5000 per night for eligible hotels.", "expected": ("5000", "5,000")},
    {"category": "semantic", "question": "How early should a normal business trip be reserved?", "document": "travel_policy.docx", "anchor": "Travel should be booked at least seven days in advance.", "expected": ("seven days", "7 days")},
    {"category": "paraphrase", "question": "What standard of communication is expected between employees and professional contacts?", "document": "employee_conduct_policy.docx", "anchor": "Employees must communicate respectfully with colleagues and professional contacts.", "expected": ("respectfully", "respect")},
    {"category": "exact_lookup", "question": "Is workplace harassment permitted?", "document": "employee_conduct_policy.docx", "anchor": "Harassment and discrimination are prohibited.", "expected": ("prohibited", "not allowed", "not permitted")},
    {"category": "semantic", "question": "What should be disclosed when a personal interest may influence a business decision?", "document": "employee_conduct_policy.docx", "anchor": "Employees must disclose potential conflicts of interest.", "expected": ("conflicts of interest", "conflict of interest")},
    {"category": "exact_lookup", "question": "What condition must emergency exits satisfy?", "document": "workplace_safety_policy.docx", "anchor": "Emergency exits must remain clear and accessible at all times.", "expected": ("clear and accessible",)},
    {"category": "paraphrase", "question": "What procedure should workers follow when the fire alarm sounds?", "document": "workplace_safety_policy.docx", "anchor": "Employees must follow building fire evacuation procedures.", "expected": ("evacuation",)},
    {"category": "keyword_heavy", "question": "PPE protective equipment designated areas", "document": "workplace_safety_policy.docx", "anchor": "Required protective equipment must be worn in designated areas.", "expected": ("designated areas",)},
    {"category": "identifier", "question": "Which MCU is the primary controller in the emergency alert system?", "document": "emergency_alert_system.docx", "anchor": "The emergency alert system uses an ESP32 microcontroller as the primary control unit.", "expected": ("esp32",)},
    {"category": "keyword_heavy", "question": "MQ-2 IR flame sensors gas fire detection", "document": "emergency_alert_system.docx", "anchor": "An MQ-2 gas sensor and an IR flame sensor are used for gas and fire detection.", "expected": ("mq-2", "ir flame")},
    {"category": "paraphrase", "question": "What escalation occurs when an alert remains unacknowledged for two minutes?", "document": "emergency_alert_system.docx", "anchor": "If an alert is not acknowledged within two minutes, the system escalates the notification to the next contact.", "expected": ("escalates", "next contact")},
    # Research-paper corpus coverage.
    {"category": "exact_lookup", "question": "What is the Transformer architecture based solely on?", "document": "Attention Is All You Need.pdf", "anchor": "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.", "expected": ("attention mechanisms",)},
    {"category": "paraphrase", "question": "What did the Transformer avoid instead of using attention-only computation?", "document": "Attention Is All You Need.pdf", "anchor": "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.", "expected": ("recurrence", "convolutions")},
    {"category": "identifier", "question": "What English-to-German WMT 2014 BLEU result is reported?", "document": "Attention Is All You Need.pdf", "anchor": "Our model achieves 28.4 BLEU on the WMT 2014", "expected": ("28.4 BLEU",)},
    {"category": "keyword_heavy", "question": "LoRA freeze pretrained weights", "document": "LORA.pdf", "anchor": "which freezes the pretrained model weights", "expected": ("pre-trained model weights",)},
    {"category": "semantic", "question": "What trainable structure does LoRA add inside Transformer layers?", "document": "LORA.pdf", "anchor": "injects trainable rank decomposition matrices into each layer of the Transformer architecture", "expected": ("trainable rank decomposition matrices",)},
    {"category": "identifier", "question": "For GPT-3 175B, by what factor can LoRA cut trainable parameters?", "document": "LORA.pdf", "anchor": "reduce the number of trainable parameters by 10,000 times", "expected": ("10,000 times",)},
    {"category": "paraphrase", "question": "Does the LoRA approach introduce extra inference latency?", "document": "LORA.pdf", "anchor": "unlike adapters, no additional inference latency", "expected": ("no additional inference latency",)},
    {"category": "exact_lookup", "question": "What alternative to full fine-tuning is proposed by the adapter work?", "document": "PEFT.pdf", "anchor": "As an alternative, we propose transfer with adapter modules.", "expected": ("adapter modules",)},
    {"category": "semantic", "question": "Are the original network parameters changed when adapter modules are used?", "document": "PEFT.pdf", "anchor": "The parameters of the original network remain fixed, yielding a high degree of parameter sharing.", "expected": ("remain fixed",)},
    {"category": "identifier", "question": "How many text classification tasks were used for the adapter evaluation?", "document": "PEFT.pdf", "anchor": "26 diverse text classification tasks", "expected": ("26",)},
    {"category": "keyword_heavy", "question": "GLUE adapter parameters per task 3.6 percent", "document": "PEFT.pdf", "anchor": "On GLUE, we attain within 0.4% of the performance of full fine-tuning, adding only 3.6% parameters per task.", "expected": ("3.6%",)},
    {"category": "semantic", "question": "What two kinds of memory are combined by RAG models?", "document": "RAG.pdf", "anchor": "models which combine pre-trained parametric and non-parametric", "expected": ("parametric", "non-parametric memory")},
    {"category": "exact_lookup", "question": "What serves as RAG's non-parametric memory in the paper?", "document": "RAG.pdf", "anchor": "We introduce RAG models where the parametric memory is a pre-trained seq2seq model and the non-parametric memory is a dense vector index of Wikipedia, accessed with a pre-trained neural retriever.", "expected": ("dense vector index of Wikipedia",)},
    {"category": "paraphrase", "question": "What advantage did RAG show over the parametric-only seq2seq baseline for generation?", "document": "RAG.pdf", "anchor": "For language generation tasks, we find that RAG models generate more specific, diverse and factual language than a state-of-the-art parametric-only seq2seq baseline.", "expected": ("more specific, diverse and factual language",)},
]

EXPANDED_NEGATIVE_CASE_DATA = [
    {"question": "What is the corporate policy for stock options?", "topic": "stock options"},
    {"question": "How many weeks of bereavement leave are guaranteed?", "topic": "bereavement leave"},
    {"question": "What is the company policy for cryptocurrency custody?", "topic": "cryptocurrency custody"},
    {"question": "What is the employee dental reimbursement limit?", "topic": "dental reimbursement"},
    {"question": "Which office provides free parking reimbursement?", "topic": "parking reimbursement"},
    {"question": "What does the Transformer paper say about employee salaries?", "topic": "employee salaries"},
    {"question": "What does LoRA recommend for vacation scheduling?", "topic": "vacation scheduling"},
    {"question": "How many GPUs does the RAG paper require for payroll processing?", "topic": "payroll processing"},
    {"question": "What is the LLaMA paper's policy on workplace harassment?", "topic": "workplace harassment"},
    {"question": "What is the emergency alert system's cafeteria menu?", "topic": "cafeteria menu"},
    {"question": "What is the annual travel budget for international holidays?", "topic": "international holiday budget"},
    {"question": "Which password manager vendor is approved by the company?", "topic": "password manager vendor"},
    {"question": "What is the remote-work policy for cryptocurrency mining?", "topic": "cryptocurrency mining"},
    {"question": "What percentage of the office rent is reimbursed?", "topic": "office rent reimbursement"},
]
