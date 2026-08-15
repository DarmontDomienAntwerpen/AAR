from aar.models import IncidentStatus
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


def test_finalize_incident_sets_status(session, sample_incident):
    aar_service.finalize_incident(session, sample_incident)
    assert sample_incident.status == IncidentStatus.FINALIZED
