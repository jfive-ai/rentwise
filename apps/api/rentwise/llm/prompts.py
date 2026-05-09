"""LLM prompts and the tool-use schema mirroring NormalizedQuery.

The schema is generated from the Pydantic model so it stays in sync if fields
are added; enums for PetPolicy / FurnishedPolicy are wired in explicitly so the
LLM is constrained to valid values.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rentwise.models import FurnishedPolicy, NormalizedQuery, PetPolicy


def _build_query_tool_schema() -> dict[str, Any]:
    json_schema = NormalizedQuery.model_json_schema()
    properties = dict(json_schema.get("properties", {}))

    # Pydantic emits $ref for enums; flatten into inline enums for LiteLLM.
    properties["pets"] = {
        "type": "string",
        "enum": [m.value for m in PetPolicy],
        "description": "User preference for pets. Default 'any' if not stated.",
    }
    properties["furnished"] = {
        "type": "string",
        "enum": [m.value for m in FurnishedPolicy],
        "description": "User preference for furnished. Default 'any' if not stated.",
    }

    # Guard: any future enum field added to NormalizedQuery will leak a $ref
    # unless it's explicitly flattened above. Fail loudly so the next maintainer
    # sees the issue at import time, not at LLM-call time.
    #
    # Pydantic emits $ref for enum fields and `anyOf: [{$ref: ...}, {type: null}]`
    # for nullable enum fields. Plain `Optional[int|str|...]` also uses anyOf but
    # without any nested $ref, so we only flag combinators that contain a $ref.
    def _contains_ref(node: Any) -> bool:
        if isinstance(node, dict):
            if "$ref" in node:
                return True
            return any(_contains_ref(v) for v in node.values())
        if isinstance(node, list):
            return any(_contains_ref(v) for v in node)
        return False

    for name, prop in properties.items():
        if isinstance(prop, dict) and _contains_ref(prop):
            raise RuntimeError(
                f"Unhandled enum/ref in NormalizedQuery field {name!r}; "
                "flatten it inline like pets/furnished."
            )

    return {
        "type": "function",
        "function": {
            "name": "submit_query",
            "description": (
                "Return the user's rental search criteria as a structured query. "
                "Only include fields the user actually mentioned; leave other "
                "fields at their defaults."
            ),
            "parameters": {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            },
        },
    }


QUERY_TOOL_SCHEMA: dict[str, Any] = _build_query_tool_schema()


# Must match `NEIGHBORHOODS` in apps/web/src/components/FilterPanel.tsx so that
# NL parses produce queries equivalent to filter-form queries. If you edit one,
# edit the other (or refactor both to read from a shared source of truth).
#
# Aligned with the City of Vancouver Open Data `local-area-boundary` names so
# every label resolves to a polygon on the backend (#92). The backend's
# `enrichment.neighborhoods` resolver also accepts common short forms
# (e.g. "Dunbar" → "Dunbar-Southlands", "Point Grey" → "West Point Grey")
# so the LLM can keep using user-friendly labels.
_NEIGHBORHOODS = [
    "Arbutus Ridge",
    "Coal Harbour",
    "Commercial Drive",
    "Downtown",
    "Dunbar",
    "East Vancouver",
    "Fairview",
    "False Creek",
    "Gastown",
    "Grandview-Woodland",
    "Kerrisdale",
    "Kitsilano",
    "Marpole",
    "Mount Pleasant",
    "Oakridge",
    "Point Grey",
    "Riley Park",
    "Shaughnessy",
    "South Cambie",
    "South Granville",
    "Strathcona",
    "Sunset",
    "West End",
    "West Point Grey",
    "Yaletown",
]

_SECONDARY_SCHOOLS = [
    "Lord Byng",
    "Sir Winston Churchill",
    "Eric Hamber",
    "Point Grey",
    "Kitsilano",
    "Magee",
    "Prince of Wales",
    "Templeton",
    "Britannia",
    "Killarney",
    "Vancouver Technical",
    "John Oliver",
    "David Thompson",
]

_SKYTRAIN_STATIONS = [
    "Waterfront",
    "Burrard",
    "Granville",
    "Stadium-Chinatown",
    "Main Street-Science World",
    "Commercial-Broadway",
    "Nanaimo",
    "29th Avenue",
    "Joyce-Collingwood",
    "Olympic Village",
    "Broadway-City Hall",
    "King Edward",
]


SYSTEM_PROMPT_EN = f"""You translate a renter's search request into a structured query by calling the `submit_query` tool.

You are operating in Vancouver, British Columbia.

Known neighborhoods: {", ".join(_NEIGHBORHOODS)}.
Known secondary school catchments: {", ".join(_SECONDARY_SCHOOLS)}.
Known SkyTrain stations: {", ".join(_SKYTRAIN_STATIONS)}.

Rules:
- Always call `submit_query` exactly once. Do not output text.
- Only set fields the user mentioned. Leave optional fields null/empty.
- For pets, use `required` if the user demands pet-friendly, `no` if they want no pets, `any` otherwise.
- For furnished, use `yes`/`no`/`any` similarly.
- "studio" means bedrooms_min=0.5.
- Prices are CAD per month. "$3000", "3000/mo", "under 3k" all mean price_max=3000.
- "available June" → first day of next occurrence of June (current year if future, else next year).
- Phrases you don't have a field for (e.g. "balcony", "in-unit laundry") go into free_text_keywords.
- If the user mentions something we have no field or keyword for (e.g. "north-facing"), you MAY still include it in free_text_keywords; the API will report any truly unsupported phrases.
"""

SYSTEM_PROMPT_KO = f"""당신은 사용자의 임대 검색 요청을 `submit_query` 도구 호출로 변환합니다.

지역은 캐나다 밴쿠버 (Vancouver, BC) 입니다.

알려진 동네: {", ".join(_NEIGHBORHOODS)}.
한국어 표기 예: 키츠/키칠라노(Kitsilano), 이스트밴(East Vancouver), 다운타운(Downtown), 코머셜(Commercial Drive), 옐레타운(Yaletown), 마운트플레전트(Mount Pleasant), 게스타운(Gastown), 페어뷰(Fairview), 마폴(Marpole).
알려진 고등학교 학군: {", ".join(_SECONDARY_SCHOOLS)}.
스카이트레인 역: {", ".join(_SKYTRAIN_STATIONS)}.

규칙:
- 반드시 `submit_query` 도구를 정확히 한 번만 호출하세요. 텍스트로 답하지 마세요.
- 사용자가 언급한 필드만 채우세요. 나머지는 null 또는 기본값.
- 반려동물: 가능 요구 시 `required`, 불가 요구 시 `no`, 그 외 `any`.
- 가구: `yes`/`no`/`any`.
- "스튜디오"는 bedrooms_min=0.5.
- 가격은 캐나다 달러/월. "3000불", "3천", "3k" 모두 price_max=3000.
- "6월 입주"는 다음 6월 1일.
- 필드에 없는 표현(예: "발코니", "세탁기 있음")은 free_text_keywords에 넣으세요.
- 우리가 지원하지 않는 표현(예: "남향")이라도 free_text_keywords에 포함시켜도 됩니다. 진짜 지원되지 않는 표현은 API가 별도로 알려줍니다.
"""


def detect_language(text: str) -> str:
    """Return 'ko' if any Hangul codepoint appears, else 'en'.

    Hangul Syllables 0xAC00-0xD7A3, Jamo 0x1100-0x11FF, Compatibility Jamo 0x3130-0x318F.
    """
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3 or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
            return "ko"
    return "en"


def pick_prompt(lang: str) -> str:
    return SYSTEM_PROMPT_KO if lang == "ko" else SYSTEM_PROMPT_EN


def render_system_prompt(lang: str, today: date) -> str:
    """Return the system prompt with today's date prepended.

    Models can't reliably guess the current date, so we inject it for any
    relative-date phrasing ("available June", "next month") to resolve correctly.
    """
    prompt = pick_prompt(lang)
    header_en = f"Today's date is {today.isoformat()} (YYYY-MM-DD)."
    header_ko = f"오늘 날짜는 {today.isoformat()} (YYYY-MM-DD) 입니다."
    header = header_ko if lang == "ko" else header_en
    return f"{header}\n\n{prompt}"
