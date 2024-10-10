from app import db


class RequestStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(36), unique=True)
    status = db.Column(db.String(20))
    webhook_url = db.Column(db.String(255))
    input_csv_url = db.Column(db.String(255))
    output_csv_url = db.Column(db.String(255))
