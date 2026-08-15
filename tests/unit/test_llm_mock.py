import json

from aar.llm.mock import MockLLMProvider
from aar.models.enums import ObservationType
from aar.schemas.extraction import ReportExtraction
from aar.schemas.findings import FindingsOutput
from aar.schemas.lessons import LessonsOutput
from aar.schemas.reconstruction import ReconstructionOutput


def _prompt_with_payload(payload: dict) -> str:
    return "Instructies.\n\nGEGEVENS (JSON):\n```json\n" + json.dumps(payload) + "\n```"


def test_mock_extraction_tags_assumption_and_uncertainty():
    payload = {
        "commander_report_id": 1,
        "sections": {
            "observations": "Bij aankomst was er zware rookontwikkeling.",
            "doubts_assumptions": (
                "Ik ging ervan uit dat de achterzijde al gecontroleerd was. "
                "Volgens mij was er niemand meer binnen."
            ),
        },
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys", user_prompt=_prompt_with_payload(payload), response_model=ReportExtraction
    )
    types = {item.observation_type for item in result.items}
    assert ObservationType.ASSUMPTION in types
    assert ObservationType.UNCERTAINTY in types
    assert ObservationType.HUMAN_OBSERVATION in types
    for item in result.items:
        assert item.source_passage  # traceability preserved


def test_mock_extraction_never_fabricates_time_not_in_text():
    payload = {
        "commander_report_id": 1,
        "sections": {"narrative": "We gingen naar binnen en zochten de bovenverdieping."},
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys", user_prompt=_prompt_with_payload(payload), response_model=ReportExtraction
    )
    assert all(item.reported_time_text is None for item in result.items)


def test_mock_extraction_captures_time_mentioned_in_text():
    payload = {
        "commander_report_id": 1,
        "sections": {"observations": "Rond 14:20 zagen we rook uit het dak komen."},
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys", user_prompt=_prompt_with_payload(payload), response_model=ReportExtraction
    )
    assert any(item.reported_time_text == "14:20" for item in result.items)


def test_mock_reconstruction_groups_by_category_with_multiple_perspectives():
    payload = {
        "observations": [
            {
                "id": 1,
                "commander_report_id": 10,
                "commander_display_name": "P12",
                "observation_type": "human_observation",
                "category": "observation",
                "content": "Zware rook zichtbaar.",
                "reported_time_text": None,
            },
            {
                "id": 2,
                "commander_report_id": 11,
                "commander_display_name": "P21",
                "observation_type": "human_observation",
                "category": "observation",
                "content": "Rook aan de achterzijde.",
                "reported_time_text": None,
            },
        ]
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys",
        user_prompt=_prompt_with_payload(payload),
        response_model=ReconstructionOutput,
    )
    assert len(result.events) == 1
    event = result.events[0]
    assert len(event.perspectives) == 2
    assert set(event.observation_ids) == {1, 2}


def test_mock_findings_generates_discussion_point_for_conflict():
    payload = {
        "observations": [
            {
                "id": 5,
                "commander_report_id": 1,
                "observation_type": "conflict",
                "category": "decision",
                "content": "P12 zegt de opdracht gegeven te hebben; P21 zegt ze niet ontvangen te hebben.",
            }
        ],
        "events": [],
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys", user_prompt=_prompt_with_payload(payload), response_model=FindingsOutput
    )
    assert len(result.discussion_points) == 1
    assert result.discussion_points[0].origin_category.value == "conflict"


def test_mock_findings_generates_positive_finding_for_went_well():
    payload = {
        "observations": [
            {
                "id": 7,
                "commander_report_id": 1,
                "observation_type": "human_observation",
                "category": "went_well",
                "content": "De coördinatie tussen P12 en P21 verliep vlot.",
            }
        ],
        "events": [],
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys", user_prompt=_prompt_with_payload(payload), response_model=FindingsOutput
    )
    assert len(result.positive_findings) == 1


def test_mock_lessons_from_discussion_points():
    payload = {
        "discussion_points": [
            {"title": "Onduidelijke opdracht", "description": "Er was verwarring over de opdracht."}
        ]
    }
    result = MockLLMProvider().generate_structured(
        system_prompt="sys", user_prompt=_prompt_with_payload(payload), response_model=LessonsOutput
    )
    assert len(result.lessons) == 1
    assert len(result.improvements) == 1
