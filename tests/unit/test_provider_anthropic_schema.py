import anthropic

from aar.llm.provider_anthropic import _require_all_fields
from aar.schemas.findings import FindingsOutput


def test_strict_schema_requires_every_field_including_defaults():
    schema = _require_all_fields(anthropic.transform_schema(FindingsOutput))

    assert set(schema["required"]) == {"discussion_points", "positive_findings", "ai_observations"}
    finding = schema["$defs"]["PositiveFindingCandidate"]
    assert set(finding["required"]) == {"title", "description", "observation_ids", "event_title"}
