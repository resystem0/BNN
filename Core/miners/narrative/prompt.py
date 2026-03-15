"""
miners/narrative/prompt.py
Prompt assembly for narrative hop generation.

Builds the full vLLM prompt from:
  • persona instruction
  • traversal path context
  • grounding chunks from the domain miner
  • prior narrative accumulated over earlier hops
"""

from __future__ import annotations

from typing import List, Optional


# ---------------------------------------------------------------------------
# Persona catalogue
# ---------------------------------------------------------------------------

PERSONAS: dict[str, str] = {
    "neutral": (
        "You are a knowledgeable guide leading the reader through a "
        "knowledge graph. Write in clear, informative prose."
    ),
    "scholar": (
        "You are a meticulous scholar. Use precise language, cite "
        "conceptual links explicitly, and maintain an academic register."
    ),
    "storyteller": (
        "You are a master storyteller. Weave facts into vivid narrative "
        "using metaphor, imagery, and a compelling arc."
    ),
    "journalist": (
        "You are an investigative journalist. Present facts crisply, "
        "connect ideas causally, and sustain a sense of discovery."
    ),
    "explorer": (
        "You are a curious explorer encountering ideas for the first time. "
        "Express wonder and make unexpected connections."
    ),
}

DEFAULT_PERSONA = "neutral"


def get_persona_instruction(persona: str) -> str:
    return PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

SYSTEM_TEMPLATE = """\
{persona_instruction}

Your task is to write ONE paragraph (the "hop") that bridges two nodes in a \
knowledge graph. The hop should:
- Naturally transition the reader from the SOURCE node to the DESTINATION node
- Be grounded in the provided reference chunks; do not invent facts
- Continue seamlessly from any prior narrative
- Be concise: {min_words}–{max_words} words
- End at a natural sentence boundary

Respond with ONLY the hop paragraph. No headings, no preamble, no commentary.\
"""

HOP_TEMPLATE = """\
## Traversal path so far
{path_str}

## Source node
{from_node}

## Destination node
{to_node}

## Reference chunks
{chunks_str}

{prior_section}\
## Your hop paragraph
"""

PRIOR_SECTION_TEMPLATE = """\
## Prior narrative (do NOT repeat; continue from here)
{prior_narrative}

"""


def build_prompt(
    from_node_id: str,
    to_node_id: str,
    path_so_far: List[str],
    chunks: List[str],
    prior_narrative: str,
    persona: str = DEFAULT_PERSONA,
    min_words: int = 80,
    max_words: int = 220,
) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for the vLLM chat completion call.
    """
    persona_instruction = get_persona_instruction(persona)

    system = SYSTEM_TEMPLATE.format(
        persona_instruction=persona_instruction,
        min_words=min_words,
        max_words=max_words,
    )

    # Path string
    if path_so_far:
        path_str = " → ".join(path_so_far)
        if from_node_id not in path_so_far:
            path_str += f" → {from_node_id}"
    else:
        path_str = from_node_id

    # Chunks — number and truncate to avoid context overflow
    MAX_CHUNKS = 5
    MAX_CHUNK_CHARS = 600
    selected = chunks[:MAX_CHUNKS]
    chunks_str = "\n\n".join(
        f"[{i+1}] {c[:MAX_CHUNK_CHARS]}{'...' if len(c) > MAX_CHUNK_CHARS else ''}"
        for i, c in enumerate(selected)
    ) if selected else "(no reference chunks provided)"

    prior_section = (
        PRIOR_SECTION_TEMPLATE.format(prior_narrative=prior_narrative.strip())
        if prior_narrative.strip()
        else ""
    )

    user = HOP_TEMPLATE.format(
        path_str=path_str,
        from_node=from_node_id,
        to_node=to_node_id,
        chunks_str=chunks_str,
        prior_section=prior_section,
    )

    return system, user


# ---------------------------------------------------------------------------
# Token budget estimator (rough heuristic: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

def estimate_prompt_tokens(system: str, user: str) -> int:
    return (len(system) + len(user)) // 4


def fits_in_context(system: str, user: str, max_tokens: int, context_limit: int = 4096) -> bool:
    prompt_tokens = estimate_prompt_tokens(system, user)
    return prompt_tokens + max_tokens <= context_limit
