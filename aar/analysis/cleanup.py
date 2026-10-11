"""On-demand text cleanup: fix typos/grammar and tighten structure on a
short facilitator-typed field (incident description, initial-call notes).
Not a pipeline stage — no persistence here, callers own saving the result."""
from __future__ import annotations

from aar.llm.base import LLMOutputValidationError, LLMProvider
from aar.llm.prompts.system_prompts import build_system_prompt
from aar.schemas.cleanup import TextCleanupOutput

_ADDENDUM = """\
TAAK: Een stukje tekst opschonen — typfouten verbeteren, structureren waar \
nuttig, duidelijk houden. Dit veld is meestal kort, maar kan ook een langere \
tekst zijn als de facilitator veel typte — behandel beide gevallen goed.

Wat je WEL mag doen: spelling/typfouten corrigeren, een rommelige zin \
herschikken tot een duidelijke zin, overbodige woorden schrappen. Bij een \
langere tekst (meerdere losse gedachten of gebeurtenissen achter elkaar): \
verdeel in korte zinnen of, indien echt nodig, korte alinea's met een \
duidelijke logische volgorde — niet alles in één lange doorlopende zin \
proppen.

Wat je NIET mag doen: geen nieuwe feiten, tijdstippen, aantallen of details \
toevoegen die niet letterlijk in de originele tekst stonden; geen \
interpretatie of duiding toevoegen; de inhoud niet inkorten door details \
weg te laten (enkel taalkundig opschonen en structureren, niet samenvatten \
— ook bij een lange tekst blijft elk feit dat erin stond behouden). Als de \
tekst al kort, duidelijk en correct is, geef ze grotendeels ongewijzigd \
terug. Zelfde taal (Nederlands) en dezelfde vaste afkortingen \
(HD/LD/SAR/SO/V+nummer) als gebruikt in de brontekst.\
"""


def build_cleanup_prompt(text: str) -> tuple[str, str]:
    system_prompt = build_system_prompt(_ADDENDUM)
    user_prompt = f"Op te schonen tekst:\n\n{text}"
    return system_prompt, user_prompt


def run_cleanup(provider: LLMProvider, text: str) -> str:
    system_prompt, user_prompt = build_cleanup_prompt(text)
    try:
        result = provider.generate_structured(
            system_prompt=system_prompt, user_prompt=user_prompt, response_model=TextCleanupOutput
        )
    except LLMOutputValidationError:
        return text
    return result.text.strip()
