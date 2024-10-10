import cloudinary
import cloudinary.uploader
import logging
import PIL.Image
import requests
#
from io import BytesIO
import pandas as pd
#
from app import db, celery
from app.models import RequestStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@celery.task
def process_images_task(request_id):
    request_entry = RequestStatus.query.filter_by(request_id=request_id, status="PENDING").first()
    if not request_entry:
        logger.error(f"Request with ID {request_id} not found or not pending.")
        return

    try:
        response = requests.get(request_entry.input_csv_url)
        response.raise_for_status()
        data = pd.read_csv(BytesIO(response.content))
    except Exception as e:
        logger.error(f"Failed to retrieve or read CSV for request {request_id}: {e}")
        request_entry.status = "FAILED"
        db.session.commit()
        return

    expected_columns = {"Serial Number", "Product Name", "Input Image Urls"}
    if not expected_columns.issubset(data.columns):
        logger.error(f"CSV for request {request_id} is missing required columns.")
        request_entry.status = "FAILED"
        db.session.commit()
        return

    request_entry.status = "PROCESSING"
    db.session.commit()

    output_csv_data = []

    for _, row in data.iterrows():
        serial_number = row["Serial Number"]
        product_name = row["Product Name"]
        image_urls = row["Input Image Urls"].split(",")
        output_image_urls = []

        index = 1

        for url in image_urls:
            try:
                response = requests.get(url)
                response.raise_for_status()

                img = PIL.Image.open(BytesIO(response.content))
                img = img.convert("RGB")

                output_image_io = BytesIO()
                img.save(output_image_io, format="JPEG", quality=50)
                output_image_io.seek(0)

                upload_response = cloudinary.uploader.upload(
                    output_image_io,
                    folder=f"processed/{request_id}/",
                    public_id=f"{serial_number}_{index}",
                    resource_type="image"
                )

                output_image_url = upload_response["secure_url"]
                output_image_urls.append(output_image_url)

            except requests.RequestException as req_err:
                logger.error(f"Network error processing {url} for request {request_id}: {req_err}")
            except PIL.UnidentifiedImageError as img_err:
                logger.error(f"Image processing error for {url} for request {request_id}: {img_err}")
            except Exception as e:
                logger.error(f"Unexpected error processing {url} for request {request_id}: {e}")
            index += 1

        output_csv_data.append([serial_number, product_name, ",".join(image_urls), ",".join(output_image_urls)])

    output_df = pd.DataFrame(output_csv_data, columns=["Serial Number", "Product Name", "Input Image Urls", "Output Image Urls"])
    output_csv_io = BytesIO()
    output_df.to_csv(output_csv_io, index=False)
    output_csv_io.seek(0)

    try:
        output_csv_response = cloudinary.uploader.upload(output_csv_io, resource_type="raw", public_id=f"output_{request_id}.csv")
        output_csv_cloudinary_url = output_csv_response["secure_url"]

        request_entry.output_csv_url = output_csv_cloudinary_url
        request_entry.status = "COMPLETED"
    except Exception as e:
        logger.error(f"Failed to upload output CSV for request {request_id}: {e}")
        request_entry.status = "FAILED"
    finally:
        db.session.commit()

    if request_entry.webhook_url:
        try:
            requests.post(request_entry.webhook_url, json={"request_id": request_id, "status": request_entry.status, "output_csv": request_entry.output_csv_url})
        except requests.RequestException as e:
            logger.error(f"Failed to send webhook for request {request_id}: {e}")
