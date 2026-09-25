"""
pipeline2/database.py
Configuration SQLAlchemy partagée pour la Pipeline 2.

Si un module `database.py` existe déjà à la racine du projet (créé par
Pipeline 1 ou 3), ce fichier peut être supprimé et les imports dans
router.py mis à jour vers `from database import get_db, SessionLocal`.
"""

from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Chemin de la base SQLite partagée (configurable via variable d'environnement)
DATABASE_URL = os.getenv("RAKABA_DB_URL", "sqlite:///./rakaba.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # nécessaire pour SQLite avec FastAPI
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI : fournit une session SQLAlchemy par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Crée les tables Pipeline 2 si elles n'existent pas encore.
    Appelé au démarrage de l'application.
    """
    from .models import Base
    Base.metadata.create_all(bind=engine)
