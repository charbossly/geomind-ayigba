# Fichier: models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
import datetime
import uuid

# On initialise SQLAlchemy ici pour pouvoir l'importer ailleurs
db = SQLAlchemy()

class ProcessingRequest(db.Model):
    __tablename__ = 'processing_requests'

    # Colonnes de la table
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='En cours')
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    image_id = db.Column(db.String(255), nullable=False, unique=True)
    
    # On utilise JSONB de PostgreSQL, c'est très performant pour stocker du JSON
    geojson_data = db.Column(JSONB, nullable=False)
    overlaps_data = db.Column(JSONB, nullable=False)

    def to_dict(self):
        """Convertit l'objet en dictionnaire pour la réponse API."""
        return {
            'id': self.id,
            'filename': self.filename,
            'status': self.status,
            'timestamp': self.timestamp.isoformat() + "Z",
            'image_id': self.image_id,
            'geojson': self.geojson_data,
            'overlaps': self.overlaps_data
        }

    def to_summary_dict(self):
        """Convertit en un dictionnaire simple pour le tableau de bord."""
        return {
            'id': self.id,
            'filename': self.filename,
            'status': self.status,
            'timestamp': self.timestamp.isoformat() + "Z"
        }