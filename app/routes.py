import cloudinary
import cloudinary.uploader
import logging
import uuid
#
from flask import Blueprint, request, jsonify
import pandas as pd
#
from app import db
from app.models import RequestStatus
from app.tasks import process_images_task
#
from .dto import UploadCSVRequestDTO, UploadCSVResponseDTO, CheckStatusRequestDTO, CheckStatusResponseDTO

main = Blueprint("main", __name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@main.route("/upload_csv", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        logger.warning("No file part in the request.")
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]

    if file.filename == "":
        logger.warning("No selected file.")
        return jsonify({"error": "No selected file"}), 400

    try:
        data = pd.read_csv(file)
        expected_columns = {"Serial Number", "Product Name", "Input Image Urls"}

        if not expected_columns.issubset(data.columns):
            logger.warning("CSV format is incorrect. Expected columns: %s", expected_columns)
            return jsonify({"error": "CSV format is incorrect. Expected columns: Serial Number, Product Name, Input Image Urls"}), 400

    except pd.errors.EmptyDataError:
        logger.error("Uploaded CSV is empty.")
        return jsonify({"error": "Uploaded CSV is empty."}), 400
    except pd.errors.ParserError:
        logger.error("Error parsing CSV file.")
        return jsonify({"error": "Error parsing CSV file."}), 400
    except Exception:
        logger.exception("Unexpected error while processing the CSV file.")
        return jsonify({"error": "An unexpected error occurred."}), 500

    file.seek(0)

    try:
        upload_response = cloudinary.uploader.upload(file, resource_type="raw")
        cloudinary_csv_url = upload_response["secure_url"]
    except Exception:
        logger.exception("Error uploading file to Cloudinary.")
        return jsonify({"error": "Error uploading file to Cloudinary."}), 500

    request_id = str(uuid.uuid4())

    try:
        dto_data = UploadCSVRequestDTO(**request.form)
    except Exception as e:
        logger.warning("Invalid request data: %s", str(e))
        return jsonify({"error": "Invalid request data."}), 400

    status_entry = RequestStatus(
        request_id=request_id,
        status="PENDING",
        input_csv_url=cloudinary_csv_url,
        webhook_url=dto_data.webhook_url
    )

    db.session.add(status_entry)
    db.session.commit()

    process_images_task.delay(request_id)

    logger.info("File uploaded successfully with request ID: %s", request_id)
    response_dto = UploadCSVResponseDTO(message="File uploaded successfully", request_id=request_id)
    return response_dto.dict(), 200


@main.route("/status/<request_id>", methods=["GET"])
def check_status(request_id):
    try:
        dto_data = CheckStatusRequestDTO(request_id=request_id)
    except Exception as e:
        logger.warning("Invalid request ID format: %s", str(e))
        return jsonify({"error": "Invalid request ID format."}), 400

    request_entry = RequestStatus.query.filter_by(request_id=dto_data.request_id).first()

    if not request_entry:
        logger.warning("Invalid request ID: %s", request_id)
        return jsonify({"error": "Invalid request ID"}), 404

    response = {
        "status": request_entry.status,
        "input_url": request_entry.input_csv_url,
        "output_path": request_entry.output_csv_url
    }

    logger.info("Status check for request ID: %s", request_id)
    response_dto = CheckStatusResponseDTO(request_id=request_id, result=response)
    return response_dto.dict(), 200
