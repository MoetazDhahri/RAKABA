"""
RAKABA Pipeline 3 - standalone Flask entry point.

Thin adapter over handlers.py: parses Flask's request shape, calls the
framework-agnostic handler, serializes the (result, status) it returns.
For the unified backend (mounted alongside Pipeline 2 under one FastAPI
process), see router.py instead - both call the same handlers.py so there's
one source of truth for the actual logic.

Two scopes, one engine:
- /api/chat/client   -> restricted, entity-scoped, escalation-aware chatbot
- /api/chat/admin    -> full-access Q&A chatbot for inspectors
- /api/investigate   -> autonomous tool-calling investigation agent
- /api/escalations   -> list flagged client questions for the admin dashboard
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(Path(__file__).resolve().parent / ".env")

import db
import handlers

app = Flask(__name__)


@app.route("/api/chat/client", methods=["POST"])
def chat_client():
    body = request.get_json(silent=True) or {}
    result, code = handlers.chat_client(
        body.get("entity_id"), body.get("message"), body.get("conversation_history", [])
    )
    return jsonify(result), code


@app.route("/api/chat/admin", methods=["POST"])
def chat_admin():
    body = request.get_json(silent=True) or {}
    result, code = handlers.chat_admin(
        body.get("inspector_id"), body.get("message"), body.get("conversation_history", [])
    )
    return jsonify(result), code


@app.route("/api/investigate", methods=["POST"])
def investigate():
    body = request.get_json(silent=True) or {}
    result, code = handlers.investigate(body.get("inspector_id"), body.get("entity_id"))
    return jsonify(result), code


@app.route("/api/escalations", methods=["GET"])
def list_escalations():
    result, code = handlers.list_escalations()
    return jsonify(result), code


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Route introuvable"}), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error("Unhandled error: %s", e)
    return jsonify({"error": "Erreur interne du serveur"}), 500


if __name__ == "__main__":
    db.get_connection()  # ensures schema exists before serving
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(debug=True, port=port)
