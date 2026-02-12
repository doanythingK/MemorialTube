from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import JobStatus


class JobCreateRequest(BaseModel):
    job_type: str = "test_render"


class CanvasJobCreateRequest(BaseModel):
    input_path: str
    output_path: str


class TransitionJobCreateRequest(BaseModel):
    image_a_path: str
    image_b_path: str
    output_path: str
    duration_seconds: Literal[6, 10]
    prompt: str
    negative_prompt: str | None = None


class LastClipJobCreateRequest(BaseModel):
    image_path: str
    output_path: str
    duration_seconds: int = Field(default=4, ge=2, le=20)
    motion_style: Literal["zoom_in", "zoom_out", "none"] = "zoom_in"


class RenderJobCreateRequest(BaseModel):
    clip_paths: list[str] = Field(min_length=1)
    output_path: str
    bgm_path: str | None = None
    bgm_volume: float = Field(default=0.15, ge=0.0, le=1.0)


class JobEnqueueResponse(BaseModel):
    job_id: str
    task_id: str
    status: JobStatus


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    status: JobStatus
    error_message: str | None
    result_message: str | None
    created_at: datetime
    updated_at: datetime
