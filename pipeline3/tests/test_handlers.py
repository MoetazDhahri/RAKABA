import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import handlers
import tools


def test_admin_chat_uses_database_tools_without_exposing_evidence():
    with patch.object(handlers, "run_tool_calling_loop", return_value=("Voici le dossier.", [{"tool": "consulter_entite"}])) as run_loop:
        result, status = handlers.chat_admin(
            "amira",
            "Que peux-tu me dire sur ENT-1 ?",
            [],
        )

    assert status == 200
    assert result == {"reply": "Voici le dossier."}
    run_loop.assert_called_once()
    assert run_loop.call_args.args[2] == handlers.tools.TOOLS_SCHEMA
    assert run_loop.call_args.args[3] == handlers.tools.TOOL_REGISTRY


def test_admin_chat_refuses_unrelated_questions_without_calling_ai():
    with patch.object(handlers, "run_tool_calling_loop") as run_loop:
        result, status = handlers.chat_admin("amira", "Qui a gagne la Champions League ?", [])

    assert status == 200
    assert "dossiers" in result["reply"]
    assert "football" in result["reply"]
    run_loop.assert_not_called()


def test_admin_chat_never_returns_fiscal_identifier_text():
    with patch.object(handlers, "run_tool_calling_loop", return_value=("Le matricule fiscal est 1234567A", [])):
        result, status = handlers.chat_admin("amira", "Dans ce dossier fiscal, donne-moi le matricule.", [])

    assert status == 200
    assert "1234567A" not in result["reply"]
    assert "matricule" not in result["reply"].lower()


def test_recent_detections_tool_is_available_to_admin_chat():
    assert "detections_recentes" in tools.TOOL_REGISTRY
    assert any(
        item["function"]["name"] == "detections_recentes"
        for item in tools.TOOLS_SCHEMA
    )


def test_admin_chat_rejects_unknown_inspector():
    result, status = handlers.chat_admin("not-authorized", "Montre-moi les dossiers récents.", [])

    assert status == 403
    assert result == {"error": "Accès inspecteur refusé"}


def test_business_name_lookup_tool_is_available():
    assert "rechercher_entite" in tools.TOOL_REGISTRY
    assert any(item["function"]["name"] == "rechercher_entite" for item in tools.TOOLS_SCHEMA)
