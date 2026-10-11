from aar.analysis.lessons import run_lessons
from aar.llm.mock import MockLLMProvider
from aar.models import DiscussionOrigin, DiscussionPoint, Improvement, Lesson


def test_run_lessons_creates_lessons_and_linked_improvements(session, sample_incident):
    # Two discussion points of the same theme (origin_category) so the mock
    # clusters them into one genuine lesson — a lesson clustering only 1
    # discussion point is deliberately suppressed (see
    # test_run_lessons_suppresses_singleton_lesson below).
    dp1 = DiscussionPoint(
        incident_id=sample_incident.id,
        title="Onduidelijke opdracht tussen P12 en P21",
        description="P12 stelt dat de opdracht gegeven werd; P21 stelt dat die niet ontvangen werd.",
        origin_category=DiscussionOrigin.CONFLICT,
    )
    dp2 = DiscussionPoint(
        incident_id=sample_incident.id,
        title="Onduidelijke opdracht tussen P21 en P30",
        description="P21 stelt dat de opdracht gegeven werd; P30 stelt dat die niet ontvangen werd.",
        origin_category=DiscussionOrigin.CONFLICT,
    )
    session.add_all([dp1, dp2])
    session.commit()

    result = run_lessons(session, sample_incident, MockLLMProvider())
    assert len(result.lessons) == 1
    assert len(result.improvements) == 1

    lessons = session.query(Lesson).filter_by(incident_id=sample_incident.id).all()
    improvements = session.query(Improvement).filter_by(incident_id=sample_incident.id).all()
    assert len(lessons) == 1
    assert len(improvements) == 1
    assert improvements[0].related_lesson_id == lessons[0].id


def test_run_lessons_suppresses_singleton_lesson(session, sample_incident):
    """A "lesson" clustering only 1 discussion point is just that point
    restated under a new heading — already fully visible on the Te
    bespreken tab, so it's deliberately dropped rather than persisted as a
    near-duplicate. Its improvement proposal still has standalone value
    though, so it's kept, just unlinked (related_lesson_id=None)."""
    dp = DiscussionPoint(
        incident_id=sample_incident.id,
        title="Onduidelijke opdracht tussen P12 en P21",
        description="P12 stelt dat de opdracht gegeven werd; P21 stelt dat die niet ontvangen werd.",
        origin_category=DiscussionOrigin.CONFLICT,
    )
    session.add(dp)
    session.commit()

    result = run_lessons(session, sample_incident, MockLLMProvider())
    assert len(result.lessons) == 1  # the LLM's raw output still proposed one

    lessons = session.query(Lesson).filter_by(incident_id=sample_incident.id).all()
    improvements = session.query(Improvement).filter_by(incident_id=sample_incident.id).all()
    assert lessons == []
    assert len(improvements) == 1
    assert improvements[0].related_lesson_id is None


def test_run_lessons_rerun_replaces_ai_but_keeps_human_added(session, sample_incident):
    dp1 = DiscussionPoint(incident_id=sample_incident.id, title="Punt A", description="Beschrijving A.")
    dp2 = DiscussionPoint(incident_id=sample_incident.id, title="Punt B", description="Beschrijving B.")
    session.add_all([dp1, dp2])
    session.commit()
    run_lessons(session, sample_incident, MockLLMProvider())

    manual_lesson = Lesson(
        incident_id=sample_incident.id, title="Handmatig leerpunt", description="Door facilitator.", is_human_added=True
    )
    session.add(manual_lesson)
    session.commit()

    run_lessons(session, sample_incident, MockLLMProvider())

    lessons = session.query(Lesson).filter_by(incident_id=sample_incident.id).all()
    assert any(l.is_human_added for l in lessons)
    ai_lessons = [l for l in lessons if not l.is_human_added]
    assert len(ai_lessons) == 1
