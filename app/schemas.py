from typing import Literal, Optional
from pydantic import BaseModel, Field


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


class ProgressResponse(BaseModel):
    task_id: str
    status: str
    percent: float
    message: str

