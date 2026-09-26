"""
pipeline2/graph.py
F2.6 — Graphe de relations inter-entités (NetworkX).

Fonctions :
  - build_graph          : construit un nx.Graph depuis une liste de liens
  - detect_clusters      : composantes connexes (fraude coordonnée)
  - get_entity_subgraph  : sous-graphe centré sur une entité
  - graph_to_db_rows     : convertit le graphe en lignes (dicts) prêtes à insérer en DuckDB
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from .models import EdgeType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structure de lien en entrée
# ---------------------------------------------------------------------------

@dataclass
class EntityLink:
    """
    Lien entre deux entités partageant un attribut commun.
    Produit une arête dans le graphe.
    """
    entity_id_a      : str
    entity_id_b      : str
    shared_attribute : str        # valeur de l'attribut partagé (ex. numéro de tél)
    link_score       : float      # confiance du lien [0, 1]
    edge_type        : str = "phone"  # "phone" | "address" | "bank_account"


# ---------------------------------------------------------------------------
# Construction du graphe
# ---------------------------------------------------------------------------

def build_graph(links: List[EntityLink]) -> nx.Graph:
    """
    Construit un graphe non orienté à partir d'une liste de liens.

    Chaque arête porte les attributs :
      - shared_attribute
      - link_score (= weight)
      - edge_type

    Paramètres
    ----------
    links : liste de EntityLink.

    Retourne
    --------
    nx.Graph avec nœuds = entity_ids, arêtes = liens partagés.
    """
    G = nx.Graph()

    for lnk in links:
        # Ajoute les nœuds s'ils n'existent pas encore
        if lnk.entity_id_a not in G:
            G.add_node(lnk.entity_id_a)
        if lnk.entity_id_b not in G:
            G.add_node(lnk.entity_id_b)

        # Ajoute (ou met à jour) l'arête
        if G.has_edge(lnk.entity_id_a, lnk.entity_id_b):
            # Cumule les attributs si plusieurs liens entre les mêmes entités
            existing = G[lnk.entity_id_a][lnk.entity_id_b]
            existing["weight"]    = max(existing["weight"], lnk.link_score)
            existing["edge_types"].add(lnk.edge_type)
        else:
            G.add_edge(
                lnk.entity_id_a,
                lnk.entity_id_b,
                weight     = lnk.link_score,
                edge_type  = lnk.edge_type,
                edge_types = {lnk.edge_type},
                shared_attribute = lnk.shared_attribute,
            )

    logger.info(
        "F2.6: graphe construit — %d nœuds, %d arêtes",
        G.number_of_nodes(), G.number_of_edges(),
    )
    return G


# ---------------------------------------------------------------------------
# Détection de clusters (composantes connexes)
# ---------------------------------------------------------------------------

@dataclass
class GraphCluster:
    """Un cluster = composante connexe du graphe."""
    cluster_id : int
    entity_ids : List[str]

    @property
    def size(self) -> int:
        return len(self.entity_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id" : self.cluster_id,
            "entity_ids" : self.entity_ids,
            "size"       : self.size,
        }


def detect_clusters(G: nx.Graph, min_size: int = 2) -> List[GraphCluster]:
    """
    Détecte les clusters (composantes connexes) dans le graphe.

    Paramètres
    ----------
    G        : graphe NetworkX.
    min_size : taille minimale d'un cluster pour être retourné (défaut 2).

    Retourne
    --------
    Liste de GraphCluster triés par taille décroissante.
    """
    clusters = []
    for idx, component in enumerate(nx.connected_components(G)):
        if len(component) >= min_size:
            clusters.append(GraphCluster(
                cluster_id = idx,
                entity_ids = sorted(component),
            ))

    # Tri par taille décroissante (les clusters les plus suspects en premier)
    clusters.sort(key=lambda c: c.size, reverse=True)
    logger.info("F2.6: %d clusters détectés (min_size=%d)", len(clusters), min_size)
    return clusters


# ---------------------------------------------------------------------------
# Sous-graphe centré sur une entité
# ---------------------------------------------------------------------------

def get_entity_subgraph(G: nx.Graph, entity_id: str, depth: int = 1) -> nx.Graph:
    """
    Extrait le sous-graphe à `depth` sauts autour de `entity_id`.

    Paramètres
    ----------
    G         : graphe complet.
    entity_id : nœud central.
    depth     : nombre de sauts (défaut 1 = voisins directs).

    Retourne le sous-graphe (view NetworkX).
    """
    if entity_id not in G:
        logger.warning("F2.6: entité %s absente du graphe.", entity_id)
        return nx.Graph()

    # BFS pour collecter les nœuds à distance <= depth
    reachable: Set[str] = {entity_id}
    frontier  = {entity_id}
    for _ in range(depth):
        next_frontier: Set[str] = set()
        for node in frontier:
            next_frontier.update(G.neighbors(node))
        new_nodes = next_frontier - reachable
        reachable.update(new_nodes)
        frontier = new_nodes
        if not frontier:
            break

    return G.subgraph(reachable).copy()


# ---------------------------------------------------------------------------
# Conversion vers lignes DB (dicts, pour persistance DuckDB)
# ---------------------------------------------------------------------------

def graph_to_db_rows(
    G: nx.Graph,
    feature_vectors: Optional[Dict[str, List[float]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Convertit un graphe NetworkX en listes de lignes (dicts) prêtes à être
    insérées dans entity_graph_nodes / entity_graph_edges (DuckDB).

    Paramètres
    ----------
    G               : graphe NetworkX.
    feature_vectors : {entity_id: [float, ...]}, vecteurs de features optionnels.

    Retourne
    --------
    (node_rows, edge_rows) — listes de dicts avec les clés des colonnes.
    """
    fv = feature_vectors or {}
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for node_id in G.nodes():
        nodes.append({
            "node_id"           : str(node_id),
            "feature_vector"    : fv.get(str(node_id), []),
            "gnn_anomaly_score" : None,  # rempli plus tard par F2.7
        })

    for u, v, data in G.edges(data=True):
        raw_type = data.get("edge_type", "phone")
        try:
            et = EdgeType(raw_type).value
        except ValueError:
            et = EdgeType.phone.value

        edges.append({
            "edge_id"   : str(uuid.uuid4()),
            "node_a"    : str(u),
            "node_b"    : str(v),
            "edge_type" : et,
            "weight"    : float(data.get("weight", 1.0)),
        })

    return nodes, edges
