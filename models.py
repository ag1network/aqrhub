from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()

class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String, nullable=False)

class LinkAggregation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(10), unique=True, nullable=False)  # Unique code for the QR
    links = db.Column(db.Text, nullable=False)  # Store links as a JSON string
