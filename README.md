# MemorialTube

Python 기반 추모영상 생성 서비스 뼈대입니다.  
현재 구성은 FastAPI + Celery + Redis + PostgreSQL + FFmpeg 입니다.

## 1. 구성

- `app/main.py`: FastAPI 진입점
- `app/api/routes/health.py`: 헬스체크 API
- `app/api/routes/jobs.py`: 테스트 작업 생성/조회 API
- `app/tasks.py`: Celery 워커 작업 (Test/Canvas/Transition/LastClip/Render)
- `app/canvas/pipeline.py`: 1600x900 캔버스 생성 + 안전검증 + 폴백
- `app/canvas/outpaint.py`: Outpainting 어댑터(`diffusers`, `mirror`)
- `app/canvas/detector.py`: 동물 감지기(`ultralytics`, `transformers`, `null`)
- `app/video/transition.py`: 생성형 전환 + 2회 실패 시 클래식 폴백
- `app/video/last_clip.py`: 마지막 사진 단독 클립 생성
- `app/video/render.py`: 클립 병합(최종 렌더, BGM 옵션)
- `docker-compose.local.yml`: 로컬 개발 실행
- `docker-compose.cloud.yml`: 클라우드 배포용 기본 틀

## 2. 빠른 시작 (로컬)

1. 환경 변수 파일 생성

```bash
cp .env.example .env
```

로컬에서 시스템 `ffmpeg`가 없으면 `.env`에 아래를 추가합니다.

```bash
FFMPEG_PATH=./bin/ffmpeg
```

2. 컨테이너 실행

```bash
make up
```

3. 상태 확인

```bash
make ps
```

4. API 헬스체크

```bash
curl http://localhost:8000/api/v1/health
```

## 3. 생성형 Outpainting/동물감지 활성화

기본 의존성(`requirements.txt`)만 설치하면 서비스는 동작하지만, 생성형 모델은 비활성일 수 있습니다.  
실제 Outpainting + 동물감지를 사용하려면 아래 의존성을 추가 설치해야 합니다.

```bash
pip install -r requirements-ai.txt
```

Docker로 AI 의존성까지 설치하려면:

```bash
docker compose -f docker-compose.local.yml build --build-arg INSTALL_AI=1
```

## 4. 테스트 작업 실행

1. 테스트 Job 생성

```bash
curl -X POST http://localhost:8000/api/v1/jobs/test \
  -H "Content-Type: application/json" \
  -d '{"job_type":"test_render"}'
```

2. Job 조회

```bash
curl http://localhost:8000/api/v1/jobs/<job_id>
```

`succeeded` 상태가 되면 워커가 `ffmpeg -version` 명령을 정상 실행한 것입니다.

## 5. TransitionJob 실행 (생성형, 6초/10초 선택)

1. 전환 Job 생성 (`duration_seconds`는 `6` 또는 `10`, `prompt` 필수)

```bash
curl -X POST http://localhost:8000/api/v1/jobs/transition \
  -H "Content-Type: application/json" \
  -d '{"image_a_path":"data/input/pet1.jpg","image_b_path":"data/input/pet2.jpg","output_path":"data/output/transition_1.mp4","duration_seconds":6,"prompt":"gentle memorial cinematic transition, soft light","negative_prompt":"extra animal, distorted pet"}'
```

```bash
curl -X POST http://localhost:8000/api/v1/jobs/transition \
  -H "Content-Type: application/json" \
  -d '{"image_a_path":"data/input/pet1.jpg","image_b_path":"data/input/pet2.jpg","output_path":"data/output/transition_1.mp4","duration_seconds":10,"prompt":"gentle memorial cinematic transition, soft light","negative_prompt":"extra animal, distorted pet"}'
```

## 6. CanvasJob 실행 (안전검증 포함)

1. 테스트 입력 이미지 준비

```bash
mkdir -p data/input data/output
# 예시: data/input/pet1.jpg
```

2. CanvasJob 생성

```bash
curl -X POST http://localhost:8000/api/v1/jobs/canvas \
  -H "Content-Type: application/json" \
  -d '{"input_path":"data/input/pet1.jpg","output_path":"data/output/pet1_canvas.jpg"}'
```

3. Job 조회

```bash
curl http://localhost:8000/api/v1/jobs/<job_id>
```

`result_message`에서 아래 정보를 확인할 수 있습니다.

- `outpaint=true/false`
- `fallback=true/false`
- `safety=true/false`
- `reason=<fallback reason>`

## 7. 안전검증 정책(현재 구현)

1. 원본 보호 영역(중앙 배치된 원본 영역) 변경 검증
2. Outpainting 실패 2회 시 안전 배경 패딩으로 폴백
3. 생성형 전환 단계는 2회 실패 시 클래식 전환으로 폴백
4. 생성 영역(좌/우 여백)에서 신규 생물 감지 시 실패 처리 후 폴백

주의:
- 동물 감지 모델이 로드되지 않은 상태에서 `STRICT_SAFETY_CHECKS=true`이면 생성형 Outpainting은 안전검증에서 실패하고 폴백됩니다.
- `OUTPAINT_PROVIDER=auto`는 `diffusers` 로딩 실패 시 `mirror`로 자동 폴백합니다.
- `TRANSITION_PROVIDER=auto`는 생성형 전환 실패 시 2회 재시도 후 클래식 전환으로 자동 폴백합니다.

## 7. LastClipJob 실행

```bash
curl -X POST http://localhost:8000/api/v1/jobs/last-clip \
  -H "Content-Type: application/json" \
  -d '{"image_path":"data/input/pet_last.jpg","output_path":"data/output/last_clip.mp4","duration_seconds":4,"motion_style":"zoom_in"}'
```

`motion_style` 선택값:
- `zoom_in`
- `zoom_out`
- `none`

## 8. RenderJob 실행 (최종 병합)

```bash
curl -X POST http://localhost:8000/api/v1/jobs/render \
  -H "Content-Type: application/json" \
  -d '{"clip_paths":["data/output/transition_1.mp4","data/output/transition_2.mp4","data/output/last_clip.mp4"],"output_path":"data/output/final.mp4"}'
```

BGM 포함 예시:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/render \
  -H "Content-Type: application/json" \
  -d '{"clip_paths":["data/output/transition_1.mp4","data/output/transition_2.mp4","data/output/last_clip.mp4"],"output_path":"data/output/final.mp4","bgm_path":"data/input/bgm.mp3","bgm_volume":0.15}'
```

## 9. PipelineJob 실행 (원클릭 전체 생성)

아래 요청 1회로 `Canvas -> Transition들 -> LastClip -> Render`를 순차 실행합니다.

```bash
curl -X POST http://localhost:8000/api/v1/jobs/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "image_paths":["data/input/pet1.jpg","data/input/pet2.jpg","data/input/pet3.jpg"],
    "working_dir":"data/work/p1",
    "final_output_path":"data/output/final_pipeline.mp4",
    "transition_duration_seconds":6,
    "transition_prompt":"gentle memorial cinematic transition, soft light",
    "transition_negative_prompt":"extra animal, distorted pet",
    "last_clip_duration_seconds":4,
    "last_clip_motion_style":"zoom_in",
    "bgm_path":"data/input/bgm.mp3",
    "bgm_volume":0.15
  }'
```

## 10. 주요 환경변수

`.env.example` 기준:

- `TARGET_FPS=24`
- `OUTPUT_PIXEL_FORMAT=yuv420p`
- `OUTPUT_VIDEO_CODEC=libx264`
- `OUTPAINT_PROVIDER=auto|diffusers|mirror`
- `OUTPAINT_MODEL_ID=<diffusers model id>`
- `OUTPAINT_DEVICE=auto|cpu|cuda`
- `OUTPAINT_MAX_ATTEMPTS=2`
- `ANIMAL_DETECTOR_PROVIDER=auto|ultralytics|transformers|null`
- `ANIMAL_DETECTOR_MODEL=<model id or path>`
- `STRICT_SAFETY_CHECKS=true|false`
- `TRANSITION_PROVIDER=auto|diffusers|classic`
- `TRANSITION_MODEL_ID=<diffusers model id>`
- `TRANSITION_MAX_ATTEMPTS=2`
- `TRANSITION_GENERATION_STEP=8` (중간 프레임 생성 간격)

## 11. 다음 구현 권장

- 품질게이트 임계값과 타임아웃 정책 확정
- 전환/렌더 단계의 품질게이트 지표 고도화
