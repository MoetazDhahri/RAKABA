"""
pipeline2/router.py
Endpoints FastAPI — Pipeline 2 : Vérifier.

Routes :
  POST   /documents/upload                — scoring complet a partir de champs declares (F2.2 sur dates declarees)
  POST   /documents/upload-file           — scoring complet a partir d'un vrai fichier PDF/image (F2.2 etendu :
                                             vraies metadonnees + structure PDF + analyse ELA, cf. document_forensics.py)
  GET    /documents/{document_id}         — détail du score (3 axes + explications)
  GET    /entities/{entity_id}/documents  — liste des documents d'une entité
  GET    /graph/entity/{entity_id}        — nœuds/arêtes liés à une entité
  GET    /graph/clusters                  — clusters détectés
  POST   /documents/{document_id}/rescan  — relance du scoring

Fonction Python pure (hors HTTP) :
  check_document_integrity(entity_id) → dict

Persistance : DuckDB partagé avec les Pipelines 1 et 3 (pipeline2/database.py).
Le graphe (entity_graph_nodes/edges) est reconstruit à la volée depuis la
table entity_links partagée de Pipeline 1 — c'est la vraie source de vérité
des liaisons d'entités (F1.6), Pipeline 2 la lit plutôt que de la dupliquer
(cf. cahier des charges §14).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from rapidfuzz import fuzz

from .database  import get_db
from .document_forensics import analyze_document_bytes, render_pdf_pages_to_images
from .ocr       import extract_text_from_image
from .graph     import (
    EntityLink,
    build_graph, detect_clusters, get_entity_subgraph, graph_to_db_rows,
)
from .gnn       import gnn_anomaly_score, is_gnn_available
from .schemas   import (
    CoherenceDetail, DocumentIn, DocumentListOut,
    EdgeTypeEnum, EntityGraphOut, GraphClusterOut,
    GraphEdgeOut, GraphNodeOut,
    IntegrityDetail, RescanOut, RiskDetail, ScoreOut,
)
from .scoring   import score_document, CompositeScore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline2", tags=["Pipeline 2 — Vérifier"])
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _normalize_document_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _extract_document_text(file_bytes: bytes, filename: str) -> str:
    """Extract a small searchable text sample for dossier suggestions.

    This is a matching aid only. The scoring pipeline still requires a human
    confirmation when the document does not identify one clear business.

    PDFs use their embedded text layer (fast, exact). A photographed
    document - which is exactly what a scanned/photographed facture is, and
    the only way a handwritten one can arrive - has no text layer at all, so
    it falls through to Tesseract OCR instead (pipeline2/ocr.py). OCR reads
    printed invoice fields (business name, printed amounts) reasonably well;
    genuine cursive handwriting is not reliably recognized by any free local
    OCR engine - see ocr.py's module docstring for why, and what it would
    take to do better.
    """
    if filename.lower().endswith(".pdf"):
        try:
            import pymupdf

            document = pymupdf.open(stream=file_bytes, filetype="pdf")
            try:
                text = "\n".join(
                    document[index].get_text()
                    for index in range(min(3, document.page_count))
                )[:12000]
            finally:
                document.close()
            if text.strip():
                return text
        except Exception:
            pass

        # No embedded text layer (a scanned PDF, i.e. a photographed page
        # saved as PDF) - render the first page to an image and OCR that,
        # same as a plain photographed image would get below.
        try:
            pages = render_pdf_pages_to_images(file_bytes, max_pages=1)
            if pages:
                return extract_text_from_image(pages[0])[:12000]
        except Exception:
            pass
        return ""

    try:
        import io

        from PIL import Image

        image = Image.open(io.BytesIO(file_bytes))
        return extract_text_from_image(image)[:12000]
    except Exception:
        return ""


FUZZY_NAME_THRESHOLD = 70  # rapidfuzz partial_ratio, 0-100


def _phone_found_in_text(text: str, phone: str) -> bool:
    """True if the listing's phone number (last 8 digits) appears anywhere in the
    document text, ignoring spacing/formatting. A phone number printed on an invoice
    is a far more reliable identifier than the business name, which for informal/
    unregistered sellers (see pipeline1/data_generator.py _UNKNOWN_BUSINESS_NAMES) is
    only a generic category label and will never appear verbatim on a real document."""
    phone_digits = re.sub(r"\D", "", phone or "")
    if len(phone_digits) < 8:
        return False
    phone_digits = phone_digits[-8:]
    text_digits = re.sub(r"\D", "", text)
    return phone_digits in text_digits


def _find_document_candidates(conn: duckdb.DuckDBPyConnection, filename: str, extracted_text: str) -> list[dict[str, Any]]:
    searchable = _normalize_document_text(f"{filename} {extracted_text}")
    rows = conn.execute(
        """
        SELECT tl.entity_id, l.business_name, l.location_text, l.phone
        FROM taxpayer_lifecycle tl
        JOIN listings l ON l.listing_id = tl.listing_id
        """
    ).fetchall()
    candidates = []
    for entity_id, business_name, location_text, phone in rows:
        name = _normalize_document_text(business_name)
        tokens = [token for token in re.findall(r"[a-z0-9]+", name) if len(token) > 2]
        matches = [token for token in tokens if token in searchable]
        phone_matched = _phone_found_in_text(extracted_text, phone)

        if matches:
            confidence = min(0.98, 0.45 + (len(matches) / max(len(tokens), 1)) * 0.5)
            matched_on = list(matches)
        elif phone_matched:
            confidence = 0.9
            matched_on = ["telephone"]
        else:
            # No exact token or phone hit: fall back to fuzzy name similarity so a
            # slightly misspelled/OCR-mangled name can still surface as a low-confidence
            # suggestion instead of no suggestion at all.
            fuzzy_score = fuzz.partial_ratio(name, searchable)
            if fuzzy_score < FUZZY_NAME_THRESHOLD:
                continue
            confidence = 0.3 + (fuzzy_score - FUZZY_NAME_THRESHOLD) / (100 - FUZZY_NAME_THRESHOLD) * 0.3
            matched_on = ["similarite_nom"]

        if phone_matched and matches:
            confidence = min(0.99, confidence + 0.1)
            matched_on.append("telephone")

        candidates.append({
            "entity_id": entity_id,
            "business_name": business_name,
            "location": location_text,
            "confidence": round(confidence, 2),
            "matched_on": matched_on,
        })
    return sorted(candidates, key=lambda candidate: candidate["confidence"], reverse=True)[:5]


@router.post("/documents/intake", summary="Préparer l'analyse d'un document sans dossier préalable")
async def intake_document(
    file: UploadFile = File(...),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Le fichier dépasse la taille maximale de 15 Mo.")
    filename = file.filename or "document"
    forensics = analyze_document_bytes(file_bytes, filename)
    extracted_text = _extract_document_text(file_bytes, filename)
    candidates = _find_document_candidates(conn, filename, extracted_text)
    return {
        "filename": filename,
        "file_type": file.content_type or "application/octet-stream",
        "text_detected": bool(extracted_text.strip()),
        "candidates": candidates,
        "forensics": forensics.to_dict(),
        "requires_confirmation": len(candidates) != 1 or candidates[0]["confidence"] < 0.8,
    }


# ---------------------------------------------------------------------------
# Helpers de lecture/écriture DuckDB (remplacent l'ORM SQLAlchemy)
# ---------------------------------------------------------------------------

def _row_to_score_out(row: Dict[str, Any]) -> ScoreOut:
    """Convertit une ligne `documents` (dict) en ScoreOut Pydantic."""
    risk_flags = json.loads(row["risk_flags"]) if row["risk_flags"] else []
    file_meta  = json.loads(row["file_metadata"]) if row["file_metadata"] else {}
    return ScoreOut(
        document_id    = row["document_id"],
        entity_id      = row["entity_id"],
        submitted_date = row["submitted_date"],
        integrity = IntegrityDetail(
            score = row["integrity_score"] if row["integrity_score"] is not None else 0.5,
            flags = json.loads(row["integrity_flags"]) if row["integrity_flags"] else [],
        ),
        coherence = CoherenceDetail(
            score        = row["coherence_score"] if row["coherence_score"] is not None else 0.5,
            raw_if_score = None,
            explanation  = "Score chargé depuis la base de données.",
        ),
        risk = RiskDetail(
            flags      = risk_flags,
            nb_flags   = len(risk_flags),
            risk_score = row["risk_score_raw"] if row["risk_score_raw"] is not None else float(len(risk_flags)),
        ),
        composite_score   = row["composite_score"] if row["composite_score"] is not None else 0.0,
        gnn_anomaly_score = gnn_anomaly_score(row["entity_id"]),
        content_forensics = file_meta.get("_content_forensics"),
    )


def _composite_to_score_out(cs: CompositeScore, content_forensics: Optional[Dict[str, Any]] = None) -> ScoreOut:
    """Convertit un CompositeScore (scoring.py) en ScoreOut Pydantic."""
    return ScoreOut(
        document_id    = cs.document_id,
        entity_id      = cs.entity_id,
        submitted_date = cs.submitted_date,
        integrity = IntegrityDetail(
            score = cs.integrity.score,
            flags = cs.integrity.flags,
        ),
        coherence = CoherenceDetail(
            score        = cs.coherence.score,
            raw_if_score = cs.coherence.raw_if_score,
            explanation  = cs.coherence.explanation,
        ),
        risk = RiskDetail(
            flags      = cs.risk.flags,
            nb_flags   = cs.risk.nb_flags,
            risk_score = cs.risk.risk_score,
        ),
        composite_score   = cs.composite_score,
        gnn_anomaly_score = cs.gnn_anomaly_score,
        content_forensics = content_forensics,
    )


def _fetch_document(conn: duckdb.DuckDBPyConnection, document_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT document_id, entity_id, file_metadata, integrity_score, coherence_score,
               risk_flags, composite_score, submitted_date, integrity_flags, risk_score_raw
        FROM documents WHERE document_id = ?
        """,
        [document_id],
    ).fetchone()
    if row is None:
        return None
    columns = ["document_id", "entity_id", "file_metadata", "integrity_score", "coherence_score",
               "risk_flags", "composite_score", "submitted_date", "integrity_flags", "risk_score_raw"]
    return dict(zip(columns, row))


def _persist_composite_score(
    cs: CompositeScore,
    file_metadata: Dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Crée ou met à jour la ligne `documents` correspondante (upsert)."""
    conn.execute("DELETE FROM documents WHERE document_id = ?", [cs.document_id])
    conn.execute(
        """
        INSERT INTO documents
            (document_id, entity_id, file_metadata, integrity_score, coherence_score,
             risk_flags, composite_score, submitted_date, integrity_flags, risk_score_raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            cs.document_id, cs.entity_id, json.dumps(file_metadata),
            cs.integrity.score, cs.coherence.score, json.dumps(cs.risk.flags),
            cs.composite_score, cs.submitted_date, json.dumps(cs.integrity.flags),
            cs.risk.risk_score,
        ],
    )


def _get_entity_historical_amounts(entity_id: str, conn: duckdb.DuckDBPyConnection) -> List[float]:
    """Récupère l'historique des montants d'une entité depuis la base.
    Le montant brut n'est pas persisté séparément ; on le relit depuis
    file_metadata quand présent (voir note dans DocumentIn)."""
    rows = conn.execute(
        "SELECT file_metadata FROM documents WHERE entity_id = ?", [entity_id]
    ).fetchall()
    amounts = []
    for (meta_json,) in rows:
        meta = json.loads(meta_json) if meta_json else {}
        if "montant" in meta:
            amounts.append(float(meta["montant"]))
    return amounts


# ---------------------------------------------------------------------------
# F2.6 — Reconstruction du graphe depuis entity_links (Pipeline 1)
# ---------------------------------------------------------------------------

def _sync_graph_from_entity_links(conn: duckdb.DuckDBPyConnection) -> None:
    """Reconstruit entity_graph_nodes/edges à partir de la table entity_links
    partagée (F1.6) — celle-ci reste la source de vérité des liaisons ;
    Pipeline 2 la lit et projette un graphe dessus, sans la dupliquer
    (cf. cahier des charges §14 : "Pipeline 2 lit entity_links, écrit
    entity_graph_nodes/edges")."""
    rows = conn.execute(
        "SELECT entity_id_a, entity_id_b, shared_attribute, link_score FROM entity_links"
    ).fetchall()

    conn.execute("DELETE FROM entity_graph_edges")
    conn.execute("DELETE FROM entity_graph_nodes")

    if not rows:
        return

    links = [
        EntityLink(
            entity_id_a=a, entity_id_b=b, shared_attribute=attr,
            link_score=score or 0.0, edge_type=attr,
        )
        for (a, b, attr, score) in rows
    ]
    G = build_graph(links)
    node_rows, edge_rows = graph_to_db_rows(G)

    for n in node_rows:
        conn.execute(
            "INSERT INTO entity_graph_nodes VALUES (?, ?, ?)",
            [n["node_id"], json.dumps(n["feature_vector"]), gnn_anomaly_score(n["node_id"])],
        )
    for e in edge_rows:
        conn.execute(
            "INSERT INTO entity_graph_edges VALUES (?, ?, ?, ?, ?)",
            [e["edge_id"], e["node_a"], e["node_b"], e["edge_type"], e["weight"]],
        )


# ---------------------------------------------------------------------------
# POST /documents/upload
# ---------------------------------------------------------------------------

@router.post(
    "/documents/upload",
    response_model=ScoreOut,
    status_code=status.HTTP_201_CREATED,
    summary="Soumettre un document et déclencher le scoring complet",
)
def upload_document(payload: DocumentIn, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> ScoreOut:
    """
    Reçoit un document fiscal, déclenche le pipeline de scoring complet
    (F2.2 + F2.3 + F2.4 + F2.5) et persiste le résultat.
    """
    doc_id = str(uuid.uuid4())

    historical = _get_entity_historical_amounts(payload.entity_id, conn)
    all_amounts = historical + [payload.montant]

    file_meta_dict = payload.file_metadata.model_dump(mode="json")
    # Le montant est nécessaire pour reconstruire l'historique côté F2.4/F2.3
    file_meta_dict["montant"] = payload.montant

    cs = score_document(
        entity_id         = payload.entity_id,
        file_metadata     = file_meta_dict,
        declared_date     = payload.declared_date,
        montant           = payload.montant,
        nb_transactions   = payload.nb_transactions,
        activite_declaree = payload.activite_declaree,
        historical_amounts= all_amounts,
        document_id       = doc_id,
    )

    cs.gnn_anomaly_score = gnn_anomaly_score(payload.entity_id)

    _persist_composite_score(cs, file_meta_dict, conn)

    logger.info("Document %s uploadé et scoré (entity=%s).", doc_id, payload.entity_id)
    return _composite_to_score_out(cs)


# ---------------------------------------------------------------------------
# POST /documents/upload-file  (F2.2 étendu : vrai fichier, pas des dates déclarées)
# ---------------------------------------------------------------------------

@router.post(
    "/documents/upload-file",
    response_model=ScoreOut,
    status_code=status.HTTP_201_CREATED,
    summary="Soumettre un vrai fichier (PDF/image) et déclencher le scoring complet",
)
async def upload_document_file(
    entity_id         : str   = Form(...),
    montant            : float = Form(...),
    nb_transactions    : int   = Form(...),
    activite_declaree  : float = Form(...),
    declared_date      : str   = Form(..., description="Date ISO, ex. 2024-03-31"),
    file               : UploadFile = File(...),
    conn: duckdb.DuckDBPyConnection = Depends(get_db),
) -> ScoreOut:
    """
    Comme /documents/upload, mais F2.2 travaille sur le VRAI fichier au lieu
    de dates déclarées par l'appelant :
      - compare declared_date aux vraies métadonnées du fichier (dates PDF
        natives ou EXIF image), plutôt qu'à un file_metadata fourni par
        l'appelant et donc potentiellement inventé ;
      - détecte si un PDF a été édité après avoir été finalisé (mises à jour
        incrémentales - flag scoré, fiable) ;
      - repère par analyse ELA des régions qui pourraient correspondre à un
        élément visuel collé (signature, cachet) - retourné dans
        `content_forensics` pour examen visuel, PAS scoré automatiquement
        (voir document_forensics.py pour pourquoi : ce signal se révèle trop
        peu fiable en test pour un verdict automatique, mais reste une bonne
        piste pour un examinateur humain).
    """
    from .integrity import _parse_dt

    doc_id = str(uuid.uuid4())
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Le fichier dépasse la taille maximale de 15 Mo.")
    filename = file.filename or "document"

    forensics = analyze_document_bytes(file_bytes, filename)

    declared_dt = _parse_dt(declared_date)
    if declared_dt is None:
        raise HTTPException(status_code=400, detail=f"declared_date invalide: {declared_date!r}")

    historical = _get_entity_historical_amounts(entity_id, conn)
    all_amounts = historical + [montant]

    file_meta_dict = {
        "filename": filename,
        "montant": montant,
        "created_at": forensics.real_created_at,
        "modified_at": forensics.real_modified_at,
    }

    # Seul le flag structurel PDF (fiable) alimente le score - le signal ELA
    # reste consultatif, voir document_forensics.py
    scored_extra_flags = [f for f in forensics.flags if f != "pasted_content_suspected"]

    cs = score_document(
        entity_id          = entity_id,
        file_metadata      = file_meta_dict,
        declared_date      = declared_dt,
        montant            = montant,
        nb_transactions    = nb_transactions,
        activite_declaree  = activite_declaree,
        historical_amounts = all_amounts,
        document_id        = doc_id,
        extra_integrity_flags = scored_extra_flags,
    )
    cs.gnn_anomaly_score = gnn_anomaly_score(entity_id)

    # file_metadata reste un blob JSON flexible - on y range aussi le detail
    # forensique complet pour eviter une migration de schema.
    persisted_meta = dict(file_meta_dict)
    persisted_meta["_content_forensics"] = forensics.to_dict()
    _persist_composite_score(cs, persisted_meta, conn)

    logger.info(
        "Document %s (fichier reel '%s') uploade et score (entity=%s, flags=%s).",
        doc_id, filename, entity_id, cs.integrity.flags,
    )
    return _composite_to_score_out(cs, content_forensics=forensics.to_dict())


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------

@router.get(
    "/documents/{document_id}",
    response_model=ScoreOut,
    summary="Récupérer le score détaillé d'un document",
)
def get_document_score(document_id: str, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> ScoreOut:
    """Retourne le détail du score d'un document (3 axes + explications)."""
    row = _fetch_document(conn, document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id!r} introuvable.",
        )
    return _row_to_score_out(row)


# ---------------------------------------------------------------------------
# GET /entities/{entity_id}/documents
# ---------------------------------------------------------------------------

@router.get(
    "/entities/{entity_id}/documents",
    response_model=DocumentListOut,
    summary="Lister tous les documents d'une entité",
)
def list_entity_documents(entity_id: str, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> DocumentListOut:
    """Liste tous les documents soumis par une entité, du plus récent au plus ancien."""
    rows = conn.execute(
        """
        SELECT document_id, entity_id, file_metadata, integrity_score, coherence_score,
               risk_flags, composite_score, submitted_date, integrity_flags, risk_score_raw
        FROM documents WHERE entity_id = ? ORDER BY submitted_date DESC
        """,
        [entity_id],
    ).fetchall()
    columns = ["document_id", "entity_id", "file_metadata", "integrity_score", "coherence_score",
               "risk_flags", "composite_score", "submitted_date", "integrity_flags", "risk_score_raw"]
    docs = [_row_to_score_out(dict(zip(columns, r))) for r in rows]
    return DocumentListOut(entity_id=entity_id, total=len(docs), documents=docs)


# ---------------------------------------------------------------------------
# GET /graph/entity/{entity_id}
# ---------------------------------------------------------------------------

@router.get(
    "/graph/entity/{entity_id}",
    response_model=EntityGraphOut,
    summary="Sous-graphe centré sur une entité",
)
def get_entity_graph(entity_id: str, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> EntityGraphOut:
    """Retourne les nœuds et arêtes directement liés à une entité."""
    _sync_graph_from_entity_links(conn)

    edges_rows = conn.execute(
        "SELECT edge_id, node_a, node_b, edge_type, weight FROM entity_graph_edges "
        "WHERE node_a = ? OR node_b = ?",
        [entity_id, entity_id],
    ).fetchall()

    neighbor_ids = {entity_id}
    for (_edge_id, a, b, _et, _w) in edges_rows:
        neighbor_ids.add(a)
        neighbor_ids.add(b)

    placeholders = ", ".join("?" for _ in neighbor_ids)
    nodes_rows = conn.execute(
        f"SELECT node_id, feature_vector, gnn_anomaly_score FROM entity_graph_nodes "
        f"WHERE node_id IN ({placeholders})",
        list(neighbor_ids),
    ).fetchall()

    nodes_out = [
        GraphNodeOut(
            node_id           = node_id,
            feature_vector    = json.loads(fv) if fv else [],
            gnn_anomaly_score = gnn_anomaly_score(node_id),
        )
        for (node_id, fv, _gnn) in nodes_rows
    ]
    edges_out = [
        GraphEdgeOut(edge_id=eid, node_a=a, node_b=b, edge_type=EdgeTypeEnum(et), weight=w)
        for (eid, a, b, et, w) in edges_rows
    ]

    return EntityGraphOut(entity_id=entity_id, nodes=nodes_out, edges=edges_out)


# ---------------------------------------------------------------------------
# GET /graph/clusters
# ---------------------------------------------------------------------------

@router.get(
    "/graph/clusters",
    response_model=List[GraphClusterOut],
    summary="Clusters d'entités détectés dans le graphe",
)
def get_clusters(conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> List[GraphClusterOut]:
    """
    Détecte et retourne les clusters (composantes connexes) du graphe complet.
    Indique le niveau de risque si au moins un nœud du cluster a un score > 0.7.
    """
    _sync_graph_from_entity_links(conn)

    all_edges = conn.execute(
        "SELECT node_a, node_b, edge_type, weight FROM entity_graph_edges"
    ).fetchall()
    if not all_edges:
        return []

    links = [
        EntityLink(entity_id_a=a, entity_id_b=b, shared_attribute=et, link_score=w, edge_type=et)
        for (a, b, et, w) in all_edges
    ]
    G        = build_graph(links)
    clusters = detect_clusters(G, min_size=2)

    result = []
    for cluster in clusters:
        placeholders = ", ".join("?" for _ in cluster.entity_ids)
        scores = conn.execute(
            f"SELECT composite_score FROM documents WHERE entity_id IN ({placeholders})",
            cluster.entity_ids,
        ).fetchall()
        max_score = max((s[0] or 0.0 for s in scores), default=0.0)
        risk_level = "high" if max_score > 0.7 else ("medium" if max_score > 0.4 else "low")

        result.append(GraphClusterOut(
            cluster_id = cluster.cluster_id,
            entity_ids = cluster.entity_ids,
            size       = cluster.size,
            risk_level = risk_level,
        ))

    return result


# ---------------------------------------------------------------------------
# POST /documents/{document_id}/rescan
# ---------------------------------------------------------------------------

@router.post(
    "/documents/{document_id}/rescan",
    response_model=RescanOut,
    summary="Relancer le scoring complet d'un document existant",
)
def rescan_document(document_id: str, conn: duckdb.DuckDBPyConnection = Depends(get_db)) -> RescanOut:
    """Relit le document depuis la base, relance le pipeline de scoring complet,
    et met à jour les scores persistés."""
    row = _fetch_document(conn, document_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id!r} introuvable.",
        )

    file_meta  = json.loads(row["file_metadata"]) if row["file_metadata"] else {}
    historical = _get_entity_historical_amounts(row["entity_id"], conn)

    montant           = float(file_meta.get("montant", 0.0))
    nb_transactions   = int(file_meta.get("nb_transactions", 1))
    activite_declaree = float(file_meta.get("activite_declaree", 1.0))
    declared_date_raw = file_meta.get("declared_date") or str(row["submitted_date"])

    from .integrity import _parse_dt
    declared_date = _parse_dt(declared_date_raw) or row["submitted_date"]

    cs = score_document(
        entity_id         = row["entity_id"],
        file_metadata     = file_meta,
        declared_date     = declared_date,
        montant           = montant,
        nb_transactions   = nb_transactions,
        activite_declaree = activite_declaree,
        historical_amounts= historical,
        document_id       = document_id,
        submitted_date    = row["submitted_date"],
    )
    cs.gnn_anomaly_score = gnn_anomaly_score(row["entity_id"])

    _persist_composite_score(cs, file_meta, conn)

    logger.info("Document %s re-scanné.", document_id)
    return RescanOut(document_id=document_id, new_score=_composite_to_score_out(cs))


# ---------------------------------------------------------------------------
# Fonction Python pure — pour l'agent d'investigation (Pipeline 3)
# ---------------------------------------------------------------------------

def check_document_integrity(entity_id: str) -> dict:
    """
    Retourne le détail structuré du dernier score composite de l'entité.

    Utilisée directement par les autres pipelines (pas d'HTTP), sur la
    connexion DuckDB partagée. Retourne un dict vide si l'entité n'a aucun
    document.
    """
    from pipeline1.db import LOCK
    from .database import get_connection

    conn = get_connection()
    try:
        with LOCK:
            row = conn.execute(
                """
                SELECT document_id, entity_id, file_metadata, integrity_score, coherence_score,
                       risk_flags, composite_score, submitted_date, integrity_flags, risk_score_raw
                FROM documents WHERE entity_id = ? ORDER BY submitted_date DESC LIMIT 1
                """,
                [entity_id],
            ).fetchone()
        if row is None:
            return {}
        columns = ["document_id", "entity_id", "file_metadata", "integrity_score", "coherence_score",
                   "risk_flags", "composite_score", "submitted_date", "integrity_flags", "risk_score_raw"]
        score_out = _row_to_score_out(dict(zip(columns, row)))
        return score_out.model_dump(mode="json")
    except Exception as exc:
        logger.error("check_document_integrity: erreur pour entity_id=%s : %s", entity_id, exc)
        return {}
