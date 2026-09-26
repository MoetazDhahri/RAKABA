"""
Groq API wrapper. Uses the OpenAI-compatible SDK pointed at
https://api.groq.com/openai/v1. Provides:
- chat(): a plain chat completion (client + admin endpoints)
- run_tool_calling_loop(): a real multi-step tool-calling loop where the
  model decides which tools to call and in what order (investigation agent)
"""

import json
import os
from datetime import datetime, timezone

from openai import OpenAI

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
# Each iteration is a full network round-trip to Groq (plus the tool's own DB
# query). Measured empirically: a real investigation using all 6 iterations
# took up to 60s end-to-end, which is what "the chatbot/document analysis
# takes ages" turned out to be. INVESTIGATION_SYSTEM_PROMPT itself only
# expects ~4 tool calls (entity, history, integrity, links) for a normal
# case, so 4 keeps that comfortably reachable while bounding the worst case.
MAX_TOOL_ITERATIONS = 4

_client = None


class GroqAPIError(Exception):
    pass


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise GroqAPIError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    return _client


def chat(system_prompt: str, conversation_history: list, user_message: str) -> str:
    """Single-turn chat completion, no tool calling. Returns the reply text."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_sanitize_history(conversation_history))
    messages.append({"role": "user", "content": user_message})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
        )
    except Exception as exc:
        raise GroqAPIError(f"Groq API call failed: {exc}") from exc

    return response.choices[0].message.content or ""


def run_tool_calling_loop(
    system_prompt: str,
    user_message: str,
    tools_schema: list,
    tool_registry: dict,
    conversation_history: list | None = None,
):
    """
    Runs a real tool-calling loop: Groq decides which tool(s) to call and in
    what order, we execute them against the real data, feed results back, and
    repeat until Groq returns a final answer with no more tool calls (or the
    iteration cap is hit).

    Returns (final_report: str, evidence_log: list[dict]).
    """
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    messages.extend(_sanitize_history(conversation_history or []))
    messages.append({"role": "user", "content": user_message})
    evidence_log = []

    try:
        client = _get_client()
    except GroqAPIError:
        raise

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
            )
        except Exception as exc:
            raise GroqAPIError(f"Groq API call failed: {exc}") from exc

        message = response.choices[0].message
        tool_calls = message.tool_calls

        if not tool_calls:
            return message.content or "", evidence_log

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            tool_fn = tool_registry.get(tool_name)
            if tool_fn is None:
                result = {"error": f"Outil inconnu: {tool_name}"}
            else:
                try:
                    result = tool_fn(**arguments)
                except Exception as exc:
                    result = {"error": f"Echec de l'outil {tool_name}: {exc}"}

            evidence_log.append(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    # Iteration cap hit: ask once more, explicitly forbidding another tool
    # call, to force a final text answer.
    #
    # Just omitting `tools` here is not enough: this model (served via Groq)
    # was fine-tuned heavily on tool use, and with several prior tool_calls/
    # tool messages already in the conversation it can still try to emit a
    # function call even when no tools are offered this turn - which the API
    # then rejects outright ("Tool choice is none, but model called a tool"),
    # turning a normal "the agent used all its steps" case into a hard 502
    # for the inspector. Passing tool_choice="none" explicitly alongside the
    # schema (rather than dropping `tools` entirely) gets far more reliable
    # compliance; if the model still misbehaves, fall back to a plain-text
    # synthesis from the evidence already gathered rather than losing the
    # whole investigation to a formatting quirk.
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL, messages=messages, tools=tools_schema, tool_choice="none",
        )
        final_text = response.choices[0].message.content or ""
    except Exception:
        final_text = _summarize_evidence_as_fallback(evidence_log)

    return final_text, evidence_log


def _summarize_evidence_as_fallback(evidence_log: list) -> str:
    """Last-resort, no-LLM-call report used only if Groq refuses to produce a
    final text answer after the tool-call budget is exhausted. Not as well
    written as a real model summary, but always available - the inspector
    gets the raw findings instead of an error page."""
    if not evidence_log:
        return (
            "Je n'ai pas pu obtenir de synthese finale du modele, et aucune donnee "
            "n'a ete recuperee. Reessayez, ou consultez le dossier directement."
        )
    lines = [
        "Synthese automatique (le modele n'a pas pu conclure lui-meme) - "
        "voici les elements bruts recueillis, a interpreter par l'inspecteur :",
        "",
    ]
    for step in evidence_log:
        lines.append(f"- {step['tool']}({step['arguments']}) -> {step['result']}")
    return "\n".join(lines)


def _sanitize_history(conversation_history):
    """Keeps only role/content, defaults role to 'user' if missing/invalid."""
    sanitized = []
    for turn in conversation_history or []:
        role = turn.get("role") if isinstance(turn, dict) else None
        content = turn.get("content") if isinstance(turn, dict) else None
        if role not in ("user", "assistant"):
            role = "user"
        if content:
            sanitized.append({"role": role, "content": content})
    return sanitized
