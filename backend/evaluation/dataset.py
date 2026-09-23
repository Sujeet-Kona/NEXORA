from dataclasses import dataclass
from pathlib import Path

from backend.services.document_chunking import (
    split_document,
)
from backend.services.document_extraction import (
    extract_document,
)

BENCHMARK_DATA_DIR = (
    Path(__file__).resolve().parents[2] / "benchmark-data"
)

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-"
    "officedocument.wordprocessingml.document"
)


@dataclass(frozen=True)
class EvaluationCase:
    question: str
    document: str
    anchor: str


@dataclass(frozen=True)
class CorpusChunk:
    id: int
    document_id: int
    document_name: str
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    organization_id: int = 1


_CASE_DATA = [
    # Leave Policy
    {
        "question": "How many days of annual leave do employees receive?",
        "document": "leave_policy.docx",
        "anchor": "Employees receive 20 days of annual leave per year.",
    },
    {
        "question": "How many days of sick leave do employees receive?",
        "document": "leave_policy.docx",
        "anchor": "Employees receive 10 days of sick leave per year.",
    },
    {
        "question": "When is manager approval required for leave?",
        "document": "leave_policy.docx",
        "anchor": "Leave requests longer than three working days require manager approval.",
    },

    # Remote Work Policy
    {
        "question": "Who is eligible to request remote work?",
        "document": "remote_work_policy.docx",
        "anchor": "Employees who have completed probation may request remote work.",
    },
    {
        "question": "How many days per week may eligible employees work remotely?",
        "document": "remote_work_policy.docx",
        "anchor": "Eligible employees may work remotely up to three days per week.",
    },
    {
        "question": "What are the core hours for remote employees?",
        "document": "remote_work_policy.docx",
        "anchor": "Remote employees must be available from 10 AM to 4 PM.",
    },

    # Information Security Policy
    {
        "question": "What authentication method must employees use?",
        "document": "information_security_policy.docx",
        "anchor": "All employees must use multi-factor authentication for supported company systems.",
    },
    {
        "question": "Can confidential information be shared outside the company without authorization?",
        "document": "information_security_policy.docx",
        "anchor": "Confidential information must not be shared outside the company without authorization.",
    },
    {
        "question": "What security protection must company devices use?",
        "document": "information_security_policy.docx",
        "anchor": "Company devices must use disk encryption and approved security software.",
    },

    # Password Authentication Policy
    {
        "question": "What is the minimum password length?",
        "document": "password_authentication_policy.docx",
        "anchor": "Passwords must contain at least 12 characters.",
    },
    {
        "question": "How often must passwords be changed?",
        "document": "password_authentication_policy.docx",
        "anchor": "Passwords must be changed every 90 days.",
    },
    {
        "question": "How many previous passwords may not be reused?",
        "document": "password_authentication_policy.docx",
        "anchor": "Employees may not reuse their previous five passwords.",
    },

    # Expense Policy
    {
        "question": "What is the daily meal expense limit?",
        "document": "expense_policy.docx",
        "anchor": "Employees may claim up to Rs. 800 per day for eligible meals incurred during approved business activity.",
    },
    {
        "question": "What expense amount requires an itemized receipt?",
        "document": "expense_policy.docx",
        "anchor": "Expenses above Rs. 500 require an itemized receipt.",
    },
    {
        "question": "Within how many days must expense reports be submitted?",
        "document": "expense_policy.docx",
        "anchor": "Expense reports must be submitted within 30 days.",
    },

    # Attendance Policy
    {
        "question": "How many working days are in the standard work week?",
        "document": "attendance_policy.docx",
        "anchor": "The standard work week consists of five working days.",
    },
    {
        "question": "When must an employee inform the manager about late arrival?",
        "document": "attendance_policy.docx",
        "anchor": "Employees arriving more than 30 minutes late must inform their manager.",
    },
    {
        "question": "How should employees record attendance?",
        "document": "attendance_policy.docx",
        "anchor": "Employees must record attendance through the company system.",
    },

    # Travel Policy
    {
        "question": "What class is normally used for domestic business flights?",
        "document": "travel_policy.docx",
        "anchor": "Domestic business travel is normally booked in economy class.",
    },
    {
        "question": "What is the hotel reimbursement limit per night?",
        "document": "travel_policy.docx",
        "anchor": "Employees may claim up to Rs. 5000 per night for eligible hotels.",
    },
    {
        "question": "How far in advance should travel normally be booked?",
        "document": "travel_policy.docx",
        "anchor": "Travel should be booked at least seven days in advance.",
    },

    # Employee Conduct Policy
    {
        "question": "How should employees communicate with colleagues and professional contacts?",
        "document": "employee_conduct_policy.docx",
        "anchor": "Employees must communicate respectfully with colleagues and professional contacts.",
    },
    {
        "question": "Is harassment and discrimination allowed?",
        "document": "employee_conduct_policy.docx",
        "anchor": "Harassment and discrimination are prohibited.",
    },
    {
        "question": "What must employees disclose when personal interests could affect business decisions?",
        "document": "employee_conduct_policy.docx",
        "anchor": "Employees must disclose potential conflicts of interest.",
    },

    # Workplace Safety Policy
    {
        "question": "What must be true of emergency exits?",
        "document": "workplace_safety_policy.docx",
        "anchor": "Emergency exits must remain clear and accessible at all times.",
    },
    {
        "question": "What should employees do during a fire alarm?",
        "document": "workplace_safety_policy.docx",
        "anchor": "Employees must follow building fire evacuation procedures.",
    },
    {
        "question": "When must required protective equipment be worn?",
        "document": "workplace_safety_policy.docx",
        "anchor": "Required protective equipment must be worn in designated areas.",
    },

    # Emergency Alert System
    {
        "question": "Which microcontroller is used by the emergency alert system?",
        "document": "emergency_alert_system.docx",
        "anchor": "The emergency alert system uses an ESP32 microcontroller as the primary control unit.",
    },
    {
        "question": "Which sensors are used for gas and fire detection?",
        "document": "emergency_alert_system.docx",
        "anchor": "An MQ-2 gas sensor and an IR flame sensor are used for gas and fire detection.",
    },
    {
        "question": "What happens if an emergency alert is not acknowledged within two minutes?",
        "document": "emergency_alert_system.docx",
        "anchor": "If an alert is not acknowledged within two minutes, the system escalates the notification to the next contact.",
    },
]


def load_cases() -> list[EvaluationCase]:
    cases = [
        EvaluationCase(
            question=case["question"],
            document=case["document"],
            anchor=case["anchor"],
        )
        for case in _CASE_DATA
    ]

    if not cases:
        raise RuntimeError("Evaluation dataset is empty")

    for case in cases:
        path = BENCHMARK_DATA_DIR / case.document

        if not path.is_file():
            raise RuntimeError(
                "Corpus file not found: " + case.document
            )

    return cases


def build_corpus_chunks() -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    chunk_id = 0

    paths = sorted(BENCHMARK_DATA_DIR.glob("*.docx"))

    if not paths:
        raise RuntimeError(
            "No corpus documents found in benchmark-data"
        )

    for document_id, path in enumerate(paths, start=1):
        extracted_document = extract_document(
            filename=path.name,
            content_type=DOCX_CONTENT_TYPE,
            content=path.read_bytes(),
        )

        for chunk_index, span in enumerate(
            split_document(extracted_document),
        ):
            chunk_id += 1

            chunks.append(
                CorpusChunk(
                    id=chunk_id,
                    document_id=document_id,
                    document_name=path.name,
                    chunk_index=chunk_index,
                    text=span.text,
                    page_start=span.page_start,
                    page_end=span.page_end,
                )
            )

    return chunks


def ground_truth_chunk_ids(
    chunks: list[CorpusChunk],
    case: EvaluationCase,
) -> set[int]:
    return {
        chunk.id
        for chunk in chunks
        if chunk.document_name == case.document
        and case.anchor in chunk.text
    }


def validate_dataset() -> None:
    cases = load_cases()
    chunks = build_corpus_chunks()

    for case in cases:
        if not ground_truth_chunk_ids(chunks, case):
            raise RuntimeError(
                "Ground truth not found for: "
                + case.question
            )
