from aar.analysis.lessons import run_lessons
from aar.llm.mock import MockLLMProvider
from aar.models import DiscussionOrigin, DiscussionPoint, Improvement, Lesson


def test_run_lessons_creates_lessons_and_linked_improvements(session, sample_incident):
    dp = DiscussionPoint(
        incident_id=sample_incident.id,
        title="Onduidelijke opdracht tussen P12 en P21",
        description="P12 stelt dat de opdracht gegeven werd; P21 stelt dat die niet ontvangen werd.",
        origin_category=DiscussionOrigin.CONFLICT,
    )
    session.add(dp)
    session.commit()

    result = run_lessons(session, sample_incident, MockLLMProvider())
    assert len(result.lessons) == 1
    assert len(result.improvements) == 1

    lessons = session.query(Lesson).filter_by(incident_id=sample_incident.id).all()
    improvements = session.query(Improvement).filter_by(incident_id=sample_incident.id).all()
    assert len(lessons) == 1
    assert len(improvements) == 1
    assert improvements[0].related_lesson_id == lessons[0].id


def test_run_lessons_rerun_replaces_ai_but_keeps_human_added(session, sample_incident):
    dp = DiscussionPoint(incident_id=sample_incident.id, title="Punt A", description="Beschrijving A.")
    session.add(dp)
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
