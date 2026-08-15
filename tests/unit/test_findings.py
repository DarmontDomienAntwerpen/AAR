from aar.analysis.findings import run_findings
from aar.llm.mock import MockLLMProvider
from aar.models import (
    CreatedBy,
    DiscussionPoint,
    Observation,
    ObservationCategory,
    ObservationType,
    PositiveFinding,
)


def _add_observation(session, incident, content, category, obs_type):
    obs = Observation(
        incident_id=incident.id,
        commander_report_id=None,
        observation_type=obs_type,
        category=category,
        content=content,
        source_passage=content,
        created_by=CreatedBy.AI,
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return obs


def test_run_findings_creates_discussion_points_and_positive_findings(session, sample_incident):
    _add_observation(
        session, sample_incident, "Ik ging ervan uit dat de achterzijde gecontroleerd was.",
        ObservationCategory.OTHER, ObservationType.ASSUMPTION,
    )
    _add_observation(
        session, sample_incident, "De coördinatie tussen P12 en P21 verliep vlot.",
        ObservationCategory.WENT_WELL, ObservationType.HUMAN_OBSERVATION,
    )

    result = run_findings(session, sample_incident, MockLLMProvider())

    assert len(result.discussion_points) == 1
    assert len(result.positive_findings) == 1

    discussion_points = session.query(DiscussionPoint).filter_by(incident_id=sample_incident.id).all()
    positive_findings = session.query(PositiveFinding).filter_by(incident_id=sample_incident.id).all()
    assert len(discussion_points) == 1
    assert len(positive_findings) == 1


def test_run_findings_rerun_replaces_ai_but_keeps_human_added(session, sample_incident):
    _add_observation(
        session, sample_incident, "Volgens mij was er niemand meer binnen.",
        ObservationCategory.OTHER, ObservationType.UNCERTAINTY,
    )
    run_findings(session, sample_incident, MockLLMProvider())

    manual_dp = DiscussionPoint(
        incident_id=sample_incident.id,
        title="Handmatig toegevoegd bespreekpunt",
        description="Door facilitator toegevoegd.",
        is_human_added=True,
    )
    session.add(manual_dp)
    session.commit()

    run_findings(session, sample_incident, MockLLMProvider())

    all_dps = session.query(DiscussionPoint).filter_by(incident_id=sample_incident.id).all()
    assert any(dp.is_human_added for dp in all_dps)
    ai_dps = [dp for dp in all_dps if not dp.is_human_added]
    assert len(ai_dps) == 1  # not duplicated across reruns


def test_run_findings_ai_observation_created_with_multiple_sources(session, sample_incident):
    o1 = Observation(
        incident_id=sample_incident.id, commander_report_id=1, observation_type=ObservationType.ASSUMPTION,
        category=ObservationCategory.OTHER, content="Ik dacht dat het al gemeld was.", source_passage="x",
        created_by=CreatedBy.AI,
    )
    o2 = Observation(
        incident_id=sample_incident.id, commander_report_id=2, observation_type=ObservationType.UNCERTAINTY,
        category=ObservationCategory.OTHER, content="Waarschijnlijk was er nog iemand binnen.", source_passage="x",
        created_by=CreatedBy.AI,
    )
    session.add_all([o1, o2])
    session.commit()

    run_findings(session, sample_incident, MockLLMProvider())

    ai_observations = (
        session.query(Observation)
        .filter_by(incident_id=sample_incident.id, observation_type=ObservationType.AI_OBSERVATION)
        .all()
    )
    assert len(ai_observations) == 1
    assert ai_observations[0].commander_report_id is None
