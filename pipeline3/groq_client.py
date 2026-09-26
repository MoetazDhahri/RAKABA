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
MAX_TOOL_ITERATIONS = 6

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
        {"role": "user", "content": user_message},
    ]
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

    # Iteration cap hit: ask once more without tools to force a final answer.
    try:
        response = client.chat.completions.create(model=GROQ_MODEL, messages=messages)
        final_text = response.choices[0].message.content or ""
    except Exception as exc:
        raise GroqAPIError(f"Groq API call failed: {exc}") from exc

    return final_text, evidence_log


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
