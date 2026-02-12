from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MemorialTube API"
    env: str = "local"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+psycopg2://memorialtube:memorialtube@postgres:5432/memorialtube"
    )
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    ffmpeg_path: str = "ffmpeg"

    target_width: int = 1600
    target_height: int = 900
    target_fps: int = 24
    output_pixel_format: str = "yuv420p"
    output_video_codec: str = "libx264"
    strict_safety_checks: bool = True
    outpaint_min_width_for_generation: int = 900
    outpaint_max_attempts: int = 2
    transition_max_attempts: int = 2

    outpaint_provider: str = "auto"  # auto|diffusers|mirror
    outpaint_model_id: str = "stabilityai/stable-diffusion-2-inpainting"
    outpaint_device: str = "auto"  # auto|cpu|cuda
    outpaint_prompt: str = (
        "clean memorial photo background extension, natural, soft light, seamless, no extra animals"
    )
    outpaint_negative_prompt: str = "extra animal, duplicate pet, distorted subject, text, watermark"
    outpaint_guidance_scale: float = 7.0
    outpaint_num_inference_steps: int = 30
    outpaint_seed: int | None = None

    animal_detector_provider: str = "auto"  # auto|ultralytics|transformers|null
    animal_detector_model: str = "yolov8n.pt"
    animal_detector_confidence_threshold: float = 0.25
    animal_detector_device: str = "auto"  # auto|cpu|cuda

    transition_provider: str = "auto"  # auto|diffusers|classic
    transition_model_id: str = "runwayml/stable-diffusion-v1-5"
    transition_device: str = "auto"  # auto|cpu|cuda
    transition_guidance_scale: float = 7.0
    transition_num_inference_steps: int = 24
    transition_strength: float = 0.35
    transition_generation_width: int = 800
    transition_generation_height: int = 450
    transition_generation_step: int = 8
    transition_allowed_extra_animals: int = 0
    transition_safety_sample_step: int = 8

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
