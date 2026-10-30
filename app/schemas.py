from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.validators import validate_task_id


class VideoInfoRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2048, description="URL video yang akan dicek")


class QualityOption(BaseModel):
    value: str
    label: str
    height: Optional[int] = None
    filesize_approx: Optional[int] = None


class VideoInfoResponse(BaseModel):
    title: str
    uploader: str
    duration: Optional[int] = None
    duration_string: str
    thumbnail: Optional[str] = None
    platform: str
    webpage_url: str
    video_qualities: list[QualityOption]
    audio_bitrates: list[int]


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2048, description="URL video yang akan diunduh")
    format_type: Literal["video", "audio"] = Field(default="video", description="Jenis unduhan: video (MP4) atau audio (MP3)")
    quality: str = Field(default="best", description="Resolusi video (best, 360, 480, 720, 1080, 1440, 2160) atau bitrate MP3 (128, 192, 256, 320)")
    task_id: Optional[str] = Field(default=None, max_length=64, description="ID tugas opsional untuk pelacakan progres real-time")

    @field_validator("task_id")
    @classmethod
    def validate_task_id_field(cls, v: Optional[str]) -> Optional[str]:
        return validate_task_id(v)


class ProgressResponse(BaseModel):
    task_id: str
    status: str
    percent: float
    message: str
