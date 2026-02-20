from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import JobStatus


class JobCreateRequest(BaseModel):
    job_type: str = "test_render"


class CanvasJobCreateRequest(BaseModel):
    input_path: str
    output_path: str
    fast_mode: bool = False
    animal_detection: bool = True


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
    clip_orders: list[int] | None = None
    output_path: str
    bgm_path: str | None = None
    bgm_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    callback_uri: str | None = None


class PipelineJobCreateRequest(BaseModel):
    image_paths: list[str] = Field(min_length=1)
    working_dir: str
    final_output_path: str
    transition_duration_seconds: Literal[6, 10] = 6
    transition_prompt: str
    transition_negative_prompt: str | None = None
    last_clip_duration_seconds: int = Field(default=4, ge=2, le=20)
    last_clip_motion_style: Literal["zoom_in", "zoom_out", "none"] = "zoom_in"
    bgm_path: str | None = None
    bgm_volume: float = Field(default=0.15, ge=0.0, le=1.0)


class JobEnqueueResponse(BaseModel):
    job_id: str
    task_id: str
    status: JobStatus


class RenderUploadEnqueueResponse(JobEnqueueResponse):
    output_path: str
    clip_count: int
    clip_orders: list[int]
    callback_uri: str | None = None


class CanvasUploadEnqueueResponse(JobEnqueueResponse):
    input_path: str
    output_path: str
    fast_mode: bool
    animal_detection: bool


class TransitionUploadEnqueueResponse(JobEnqueueResponse):
    image_a_path: str
    image_b_path: str
    output_path: str
    duration_seconds: int


class LastClipUploadEnqueueResponse(JobEnqueueResponse):
    input_path: str
    output_path: str
    duration_seconds: int
    motion_style: str


class PipelineUploadEnqueueResponse(JobEnqueueResponse):
    image_count: int
    working_dir: str
    output_path: str
    bgm_path: str | None = None


class JobRuntimeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    stage: str
    progress_percent: int
    detail_message: str | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    status: JobStatus
    error_message: str | None
    result_message: str | None
    created_at: datetime
    updated_at: datetime
    stage: str | None = None
    progress_percent: int | None = None
    detail_message: str | None = None
    cancel_requested: bool | None = None


class JobCancelResponse(BaseModel):
    job_id: str
    status: JobStatus
    cancel_requested: bool
    stage: str
    progress_percent: int
    detail_message: str | None


class ProjectCreateRequest(BaseModel):
    name: str
    transition_duration_seconds: Literal[6, 10] = 6
    transition_prompt: str
    transition_negative_prompt: str | None = None
    last_clip_duration_seconds: int = Field(default=4, ge=2, le=20)
    last_clip_motion_style: Literal["zoom_in", "zoom_out", "none"] = "zoom_in"
    bgm_path: str | None = None
    bgm_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    final_output_path: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    transition_duration_seconds: int
    transition_prompt: str
    transition_negative_prompt: str | None
    last_clip_duration_seconds: int
    last_clip_motion_style: str
    bgm_path: str | None
    bgm_volume: float
    final_output_path: str | None
    created_at: datetime
    updated_at: datetime


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    order_index: int
    file_name: str
    file_path: str
    width: int
    height: int
    created_at: datetime


class ProjectRunRequest(BaseModel):
    working_dir: str | None = None
    final_output_path: str | None = None
