import aiohttp
import asyncio
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
    asyncio.run(process_images_async(request_id))


async def process_images_async(request_id):
    request_entry = RequestStatus.query.filter_by(request_id=request_id, status="PENDING").first()
    if not request_entry:
        logger.error(f"Request with ID {request_id} not found or not pending.")
        return

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(request_entry.input_csv_url) as response:
                response.raise_for_status()
                data = pd.read_csv(BytesIO(await response.read()))
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

            tasks = []
            for index, url in enumerate(image_urls, start=1):
                tasks.append(process_image(session, url, serial_number, index, output_image_urls))

            await asyncio.gather(*tasks)

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
                async with session.post(request_entry.webhook_url, json={"request_id": request_id, "status": request_entry.status, "output_csv": request_entry.output_csv_url}) as webhook_response:
                    webhook_response.raise_for_status()
            except aiohttp.ClientError as e:
                logger.error(f"Failed to send webhook for request {request_id}: {e}")


async def process_image(session, url, serial_number, index, output_image_urls):
    try:
        async with session.get(url) as response:
            response.raise_for_status()

            img = PIL.Image.open(BytesIO(await response.read()))
            img = img.convert("RGB")

            output_image_io = BytesIO()
            img.save(output_image_io, format="JPEG", quality=50)
            output_image_io.seek(0)

            upload_response = cloudinary.uploader.upload(
                output_image_io,
                folder=f"processed/{serial_number}/",
                public_id=f"{serial_number}_{index}",
                resource_type="image"
            )

            output_image_url = upload_response["secure_url"]
            output_image_urls.append(output_image_url)

    except aiohttp.ClientError as req_err:
        logger.error(f"Network error processing {url} for request: {req_err}")
    except PIL.Image.UnidentifiedImageError as img_err:
        logger.error(f"Image processing error for {url}: {img_err}")
    except Exception as e:
        logger.error(f"Unexpected error processing {url}: {e}")
