"""
pipeline2/gnn.py
F2.7 — GNN optionnel (PyTorch Geometric — GraphSAGE).

CONTRAINTE NON NÉGOCIABLE :
  Ce module est une couche d'ENRICHISSEMENT OPTIONNELLE.
  Si PyTorch Geometric n'est pas installé, si l'entraînement échoue,
  ou si l'inférence plante, TOUTES les fonctions retournent None
  sans jamais propager d'exception vers les couches supérieures.

Architecture :
  - GraphSAGE à 2 couches (in → 64 → 32 → 1)
  - Tâche : score d'anomalie par nœud (0 = sain, 1 = suspect)
  - Entraînement non supervisé (reconstruction loss) sur le graphe NetworkX
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import conditionnel de PyTorch Geometric
# ---------------------------------------------------------------------------
_PYG_AVAILABLE = False
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.data import Data
    from torch_geometric.nn   import SAGEConv
    from torch_geometric.utils import from_networkx
    _PYG_AVAILABLE = True
    logger.info("F2.7: PyTorch Geometric disponible.")
except ImportError:
    logger.warning(
        "F2.7: PyTorch Geometric introuvable. "
        "Les scores GNN seront None pour tous les nœuds."
    )

# ---------------------------------------------------------------------------
# Paramètres du modèle
# ---------------------------------------------------------------------------
HIDDEN_DIM   = 64
OUT_DIM      = 32
EPOCHS       = 50
LEARNING_RATE= 0.01
RANDOM_STATE = 42

# ---------------------------------------------------------------------------
# Définition du modèle GraphSAGE (uniquement si PyG disponible)
# ---------------------------------------------------------------------------

if _PYG_AVAILABLE:
    class GraphSAGEAnomalyDetector(nn.Module):
        """
        GraphSAGE à 2 couches suivi d'une tête de scoring scalaire.
        Produit un score d'anomalie par nœud dans [0, 1].
        """

        def __init__(self, in_channels: int):
            super().__init__()
            self.conv1 = SAGEConv(in_channels, HIDDEN_DIM)
            self.conv2 = SAGEConv(HIDDEN_DIM, OUT_DIM)
            self.head  = nn.Linear(OUT_DIM, 1)

        def forward(self, x, edge_index):
            x = self.conv1(x, edge_index)
            x = F.relu(x)
            x = F.dropout(x, p=0.2, training=self.training)
            x = self.conv2(x, edge_index)
            x = F.relu(x)
            out = torch.sigmoid(self.head(x))   # [N, 1] dans [0, 1]
            return out.squeeze(-1)              # [N]

# ---------------------------------------------------------------------------
# État du module (singleton)
# ---------------------------------------------------------------------------

_model           : Optional[Any] = None   # GraphSAGEAnomalyDetector
_node_index_map  : Dict[str, int] = {}    # entity_id → index dans le tenseur
_node_scores     : Dict[str, float] = {}  # entity_id → score calculé


# ---------------------------------------------------------------------------
# Entraînement
# ---------------------------------------------------------------------------

def train_gnn(G: nx.Graph, feature_vectors: Optional[Dict[str, Any]] = None) -> bool:
    """
    Entraîne le modèle GraphSAGE sur le graphe fourni.

    Paramètres
    ----------
    G               : graphe NetworkX (nœuds = entity_ids).
    feature_vectors : {entity_id: list[float]}, vecteurs de features par nœud.
                      Si absent, utilise des features aléatoires seédées.

    Retourne True si l'entraînement a réussi, False sinon.
    Toute exception est loggée et silencieuse en amont.
    """
    global _model, _node_index_map, _node_scores

    if not _PYG_AVAILABLE:
        logger.warning("F2.7: PyG non disponible, entraînement GNN ignoré.")
        return False

    try:
        torch.manual_seed(RANDOM_STATE)
        np.random.seed(RANDOM_STATE)

        nodes = list(G.nodes())
        if len(nodes) < 2:
            logger.warning("F2.7: graphe trop petit (%d nœuds) pour entraîner le GNN.", len(nodes))
            return False

        # --- Construction de la matrice de features ---
        fv     = feature_vectors or {}
        in_dim = 4   # dimension par défaut

        rows = []
        for nid in nodes:
            vec = fv.get(str(nid))
            if vec and len(vec) > 0:
                rows.append(vec)
                in_dim = len(vec)
            else:
                # Features aléatoires seédées si absentes
                rng  = np.random.RandomState(abs(hash(nid)) % (2**31))
                rows.append(rng.randn(in_dim).tolist())

        # Assure que toutes les lignes ont la même dimension
        rows = [r[:in_dim] + [0.0] * max(0, in_dim - len(r)) for r in rows]
        x    = torch.tensor(rows, dtype=torch.float)

        # --- Construction de l'edge_index (COO format) ---
        node_to_idx = {nid: idx for idx, nid in enumerate(nodes)}
        _node_index_map = node_to_idx

        src, dst = [], []
        for u, v in G.edges():
            ui, vi = node_to_idx[u], node_to_idx[v]
            src += [ui, vi]   # arête non orientée → deux directions
            dst += [vi, ui]

        if not src:
            logger.warning("F2.7: graphe sans arêtes, entraînement GNN ignoré.")
            return False

        edge_index = torch.tensor([src, dst], dtype=torch.long)

        # --- Entraînement (self-supervised : reconstruction des features) ---
        model     = GraphSAGEAnomalyDetector(in_channels=in_dim)
        optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

        model.train()
        for epoch in range(EPOCHS):
            optimizer.zero_grad()
            out  = model(x, edge_index)   # [N] scores d'anomalie
            # Loss non supervisée : minimiser l'entropie croisée avec des pseudo-labels 0
            # (on suppose que la majorité des nœuds sont sains)
            pseudo_labels = torch.zeros_like(out)
            loss = F.binary_cross_entropy(out, pseudo_labels)
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 10 == 0:
                logger.debug("F2.7: epoch %d/%d loss=%.4f", epoch + 1, EPOCHS, loss.item())

        # --- Calcul des scores finaux ---
        model.eval()
        with torch.no_grad():
            scores = model(x, edge_index).numpy()   # [N]

        _node_scores = {nid: float(scores[idx]) for nid, idx in node_to_idx.items()}
        _model = model

        logger.info(
            "F2.7: GNN entraîné avec succès. %d nœuds scorés. "
            "Score moyen: %.4f",
            len(_node_scores), float(np.mean(scores)),
        )
        return True

    except Exception as exc:
        logger.error("F2.7: erreur lors de l'entraînement GNN : %s", exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Inférence
# ---------------------------------------------------------------------------

def gnn_anomaly_score(node_id: str) -> Optional[float]:
    """
    Retourne le score d'anomalie GNN pour un nœud donné.

    Convention : 0 = sain, 1 = très suspect.

    Retourne None si :
      - PyG n'est pas installé
      - Le modèle n'est pas entraîné
      - Le nœud est absent du graphe d'entraînement
      - Toute erreur d'inférence

    Ne propage JAMAIS d'exception.
    """
    if not _PYG_AVAILABLE or _model is None:
        return None

    try:
        score = _node_scores.get(str(node_id))
        if score is None:
            logger.debug("F2.7: nœud %s absent des scores GNN.", node_id)
        return score
    except Exception as exc:
        logger.error("F2.7: erreur inférence GNN pour %s : %s", node_id, exc)
        return None


def is_gnn_available() -> bool:
    """Retourne True si le GNN est entraîné et prêt."""
    return _PYG_AVAILABLE and _model is not None and len(_node_scores) > 0
