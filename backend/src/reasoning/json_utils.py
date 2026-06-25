"""
ESGenuine — lenient JSON parsing for LLM output
================================================
8B-class models often wrap their JSON in ```fences``` or add a preamble/trailing note,
which makes a bare `json.loads` fail ~5% of the time and lose the whole answer. This
recovers the JSON object from that noise. Pure (json + re only) so any module — including
the import-light fact-check layer — can use it without pulling heavy deps.
"""

import json
import re


def loads_lenient(raw):
    """Parse a JSON object from an LLM response, tolerating code fences / surrounding prose.

    Order: strip a leading/trailing ``` fence and try strict parse; on failure, extract the
    outermost {...} span and parse that. Raises ValueError if nothing parses (callers keep
    their existing except-branch fallbacks)."""
    if raw is None:
        raise ValueError("empty LLM response")
    s = str(raw).strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)   # first '{' … last '}'
    if m:
        return json.loads(m.group(0))        # may still raise → caller's fallback handles it
    raise ValueError("no JSON object found in LLM response")
