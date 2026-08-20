from aar.models import IncidentEvent, IncidentStatus, Observation
from aar.models.enums import CreatedBy, ObservationCategory, ObservationType
from aar.services import aar_service


def test_add_and_delete_manual_event(session, sample_incident):
    event = aar_service.add_manual_event(session, sample_incident, "Extra moment door facilitator")
    assert event.is_human_added
    assert event.order_index == 0

    events = aar_service.get_events(session, sample_incident)
    assert len(events) == 1

    aar_service.delete_event(session, event)
    assert aar_service.get_events(session, sample_incident) == []


def test_update_event_summary(session, sample_incident):
    event = aar_service.add_manual_event(session, sample_incident, "Titel")
    aar_service.update_event_summary(session, event, "  Nieuwe samenvatting.  ")
    assert event.ai_summary == "Nieuwe samenvatting."


def test_add_manual_discussion_point_and_delete(session, sample_incident):
    dp = aar_service.add_manual_discussion_point(session, sample_incident, "Titel", "Beschrijving")
    assert dp.is_human_added
    assert len(aar_service.get_discussion_points(session, sample_incident)) == 1
    aar_service.delete_discussion_point(session, dp)
    assert aar_service.get_discussion_points(session, sample_incident) == []


def test_add_correction_bumps_status_from_analyzed_to_in_review(session, sample_incident):
    sample_incident.status = IncidentStatus.ANALYZED
    session.commit()

    aar_service.add_correction(session, sample_incident, "event", None, "Dit was geen tegenstelling.")

    assert sample_incident.status == IncidentStatus.IN_REVIEW


def test_default_situation_summary_combines_event_summaries(session, sample_incident):
    e1 = aar_service.add_manual_event(session, sample_incident, "Aankomst")
    aar_service.update_event_summary(session, e1, "Eerste voertuig ter plaatse.")
    e2 = aar_service.add_manual_event(session, sample_incident, "Opschaling")
    aar_service.update_event_summary(session, e2, "Opschaling naar tweede alarm.")

    summary = aar_service.default_situation_summary(session, sample_incident)
    assert "Eerste voertuig ter plaatse." in summary
    assert "Opschaling naar tweede alarm." in summary


def test_default_situation_summary_matches_on_observation_category_not_title(session, sample_incident):
    """Regression: a real LLM gives events specific, content-derived titles
    (never the bare category label), so the "crucial" filter must look at
    the category of the event's underlying observations, not the event's
    own title — matching on title left the summary permanently empty."""
    decision_obs = Observation(
        incident_id=sample_incident.id,
        observation_type=ObservationType.HUMAN_OBSERVATION,
        category=ObservationCategory.DECISION,
        content="Beslissing tot opschaling.",
        source_passage="Beslissing tot opschaling.",
        created_by=CreatedBy.AI,
    )
    trivial_obs = Observation(
        incident_id=sample_incident.id,
        observation_type=ObservationType.HUMAN_OBSERVATION,
        category=ObservationCategory.OTHER,
        content="Er stond een geparkeerde auto voor de deur.",
        source_passage="Er stond een geparkeerde auto voor de deur.",
        created_by=CreatedBy.AI,
    )
    session.add_all([decision_obs, trivial_obs])
    session.commit()

    crucial_event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Beslissing opschaling en zoekactie P34",
        order_index=0,
        ai_summary="P34 opgeschaald voor zoekactie.",
        observation_ids=[decision_obs.id],
    )
    trivial_event = IncidentEvent(
        incident_id=sample_incident.id,
        title="Aankomst P12, geparkeerde auto voor deur",
        order_index=1,
        ai_summary="Geparkeerde auto gezien bij aankomst.",
        observation_ids=[trivial_obs.id],
    )
    session.add_all([crucial_event, trivial_event])
    session.commit()

    summary = aar_service.default_situation_summary(session, sample_incident)
    assert "Beslissing opschaling en zoekactie P34" in summary
    assert "Aankomst P12, geparkeerde auto voor deur" not in summary


def test_finalize_incident_sets_status(session, sample_incident):
    aar_service.finalize_incident(session, sample_incident)
    assert sample_incident.status == IncidentStatus.FINALIZED
