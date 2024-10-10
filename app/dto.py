from pydantic import BaseModel, HttpUrl
from typing import Optional


class UploadCSVRequestDTO(BaseModel):
    webhook_url: Optional[HttpUrl]


class UploadCSVResponseDTO(BaseModel):
    message: str
    request_id: str


class CheckStatusRequestDTO(BaseModel):
    request_id: str


class CheckStatusResponseDTO(BaseModel):
    request_id: str
    result: dict
