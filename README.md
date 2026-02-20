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

1. 로컬 셋업 스크립트 실행 (권장)

```bash
chmod +x setup.sh
./setup.sh
```

AI 의존성까지 함께 설치하려면:

```bash
./setup.sh --with-ai
```

2. 환경 변수 파일 생성

```bash
cp .env.example .env
```

로컬에서 시스템 `ffmpeg`가 없으면 `.env`에 아래를 추가합니다.

```bash
FFMPEG_PATH=./bin/ffmpeg
```

3. 컨테이너 실행

```bash
make up
```

4. 상태 확인

```bash
make ps
```

5. API 헬스체크

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

`MT5Tokenizer` 관련 import 오류가 나오면(예: `cannot import name 'MT5Tokenizer'`), 아래 복구 스크립트를 실행하세요.

```bash
chmod +x scripts/fix_ai_env.sh
./scripts/fix_ai_env.sh
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
  -d '{"input_path":"data/input/pet1.jpg","output_path":"data/output/pet1_canvas.jpg","fast_mode":false,"animal_detection":true}'
```

옵션 설명:
- `fast_mode=true`: outpainting step을 `12`로 고정
- `fast_mode=true`: outpainting 재시도 횟수를 `1회`로 제한(빠른 종료)
- `fast_mode=true`: outpainting 생성 해상도 긴 변을 `OUTPAINT_FAST_MAX_SIDE`(기본 640)로 제한 후 결과를 원본 캔버스로 복원
- `fast_mode=false`: 기존 설정값(`OUTPAINT_NUM_INFERENCE_STEPS`) 사용
- `animal_detection=true`: 동물 검출 안전검사 사용
- `animal_detection=false`: 동물 검출 안전검사 미사용

3. Job 조회

```bash
curl http://localhost:8000/api/v1/jobs/<job_id>
```

`result_message`에서 아래 정보를 확인할 수 있습니다.

- `outpaint=true/false`
- `adapter=<DiffusersOutpaintAdapter|MirrorOutpaintAdapter|none>`
- `fallback=true/false`
- `safety=true/false`
- `reason=<fallback reason>`

## 7. 안전검증 정책(현재 구현)

1. 원본 보호 영역(중앙 배치된 원본 영역) 변경 검증
2. Outpainting 실패 2회 시 안전 배경 패딩으로 폴백
3. 생성형 전환 단계는 2회 실패 시 클래식 전환으로 폴백
4. 생성 영역(좌/우 여백)에서 신규 생물 감지 시 실패 처리 후 폴백
5. 생성 경계(원본-확장 영역) 이음새 위화감이 크면 실패 처리 후 폴백
6. 늘어난 영역(좌/우 생성영역) 전체의 톤/질감이 인접 원본 영역과 크게 어긋나면 실패 처리 후 폴백

주의:
- 동물 감지 모델이 로드되지 않은 상태에서 `STRICT_SAFETY_CHECKS=true`이면 생성형 Outpainting은 안전검증에서 실패하고 폴백됩니다.
- `OUTPAINT_PROVIDER=auto`는 `diffusers` 로딩 실패 시 `mirror`로 자동 폴백합니다.
- `MirrorOutpaintAdapter`가 선택되면 미러 결과를 그대로 저장하지 않고 안전 배경 캔버스로 강제 폴백합니다.
- `TRANSITION_PROVIDER=auto`는 생성형 전환 실패 시 2회 재시도 후 클래식 전환으로 자동 폴백합니다.
- `CANVAS_BACKGROUND_STYLE=reflect`를 명시하지 않으면, 안전 배경은 미러 패턴 대신 `cover`(또는 `blur`)로 생성됩니다.
- Outpainting 판단은 내용 종류(예: 꽃 유무) 자체를 금지하지 않고, 경계 위화감 + 생성영역 전체 자연스러움 기준으로 수행됩니다.

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
  -d '{"clip_paths":["data/output/transition_1.mp4","data/output/transition_2.mp4","data/output/last_clip.mp4"],"clip_orders":[2,1,3],"output_path":"data/output/final.mp4"}'
```

BGM 포함 예시:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/render \
  -H "Content-Type: application/json" \
  -d '{"clip_paths":["data/output/transition_1.mp4","data/output/transition_2.mp4","data/output/last_clip.mp4"],"output_path":"data/output/final.mp4","bgm_path":"data/input/bgm.mp3","bgm_volume":0.15}'
```

## 8.1 동영상 업로드 병합 화면

브라우저에서 아래 주소를 열면 동영상 파일 업로드 후 병합 요청을 보낼 수 있습니다.

```text
http://127.0.0.1:8000/api/v1/jobs/render/upload-ui
```

화면에서:
- 동영상 2개 이상 업로드
- 영상 로우를 선택하면 해당 로우의 화살표가 나타나며, 그 화살표로 병합 순서 조정
- (선택) BGM 업로드
- 출력 파일명 입력
- 병합 요청 후 Job 상태 자동 갱신 확인

참고:
- 업로드된 파일은 `data/input/uploads/render_ui/<요청ID>/`에 저장됩니다.
- 결과 파일은 `data/output/`에 생성됩니다.
- 결과 다운로드 주소 형식: `/api/v1/jobs/render/output/{file_name}`
- `callback_uri`를 입력하면 병합 완료 시 `download_uri` 포함 JSON을 해당 URI로 POST 전송합니다.

## 8.2 기타 업로드 화면

업로드 화면 모음:

```text
http://127.0.0.1:8000/api/v1/jobs/upload-ui
```

개별 화면:

```text
http://127.0.0.1:8000/api/v1/jobs/canvas/upload-ui
http://127.0.0.1:8000/api/v1/jobs/transition/upload-ui
http://127.0.0.1:8000/api/v1/jobs/last-clip/upload-ui
http://127.0.0.1:8000/api/v1/jobs/pipeline/upload-ui
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

## 10. Project 기반 실행(업로드 -> 실행)

1. 프로젝트 생성

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name":"memorial-project-001",
    "transition_duration_seconds":6,
    "transition_prompt":"gentle memorial cinematic transition, soft light",
    "transition_negative_prompt":"extra animal, distorted pet",
    "last_clip_duration_seconds":4,
    "last_clip_motion_style":"zoom_in",
    "bgm_path":"data/input/bgm.mp3",
    "bgm_volume":0.15
  }'
```

2. 이미지 업로드(멀티파트)

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/assets \
  -F "order_index=0" \
  -F "file=@data/input/pet1.jpg"
```

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/assets \
  -F "order_index=1" \
  -F "file=@data/input/pet2.jpg"
```

3. 프로젝트 실행(원클릭)

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/run \
  -H "Content-Type: application/json" \
  -d '{}'
```

4. 프로젝트 실행 취소

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/cancel
```

## 11. 주요 환경변수

`.env.example` 기준:

- `TARGET_FPS=24`
- `OUTPUT_PIXEL_FORMAT=yuv420p`
- `OUTPUT_VIDEO_CODEC=libx264`
- `OUTPAINT_PROVIDER=auto|diffusers|mirror`
- `OUTPAINT_MODEL_ID=<diffusers model id>`
- `OUTPAINT_DEVICE=auto|cpu|cuda`
- `OUTPAINT_MIN_WIDTH_FOR_GENERATION=640` (이 폭 미만은 outpaint 스킵 후 안전 배경 사용)
- `OUTPAINT_MAX_ATTEMPTS=2`
- `CANVAS_BACKGROUND_STYLE=cover|blur` (기본 `cover`, `blur`는 블러 패딩)
- `CANVAS_BACKGROUND_BLUR_RADIUS=22` (`CANVAS_BACKGROUND_STYLE=blur`일 때 사용)
- `CANVAS_EDGE_BLEND_PX=24` (중앙 원본과 좌우 배경 경계 블렌딩 폭)
- `ANIMAL_DETECTOR_PROVIDER=auto|ultralytics|transformers|null`
- `ANIMAL_DETECTOR_MODEL=<model id or path>`
- `STRICT_SAFETY_CHECKS=true|false`
- `TRANSITION_PROVIDER=auto|diffusers|classic`
- `TRANSITION_MODEL_ID=<diffusers model id>`
- `TRANSITION_MAX_ATTEMPTS=2`
- `TRANSITION_GENERATION_STEP=8` (중간 프레임 생성 간격)
- `STORAGE_ROOT=data/storage` (프로젝트 업로드 파일 저장 루트)

경로 정책:
- API로 전달하는 입력/출력 경로는 `data/` 또는 `STORAGE_ROOT` 하위만 허용됩니다.
- 경로가 허용 루트를 벗어나면 요청이 거부됩니다.

진행률/취소 API:
- `GET /api/v1/jobs/{job_id}`: `stage`, `progress_percent`, `detail_message`, `cancel_requested` 포함
- `GET /api/v1/jobs/{job_id}/runtime`: runtime 상세만 조회
- `POST /api/v1/jobs/{job_id}/cancel`: 개별 작업 취소 요청
- `POST /api/v1/projects/{project_id}/cancel`: 프로젝트의 현재 실행 작업 취소 요청
- `POST /api/v1/jobs/render/upload`: 동영상 multipart 업로드 + 병합 Job 등록
  - form 필드 `callback_uri`(선택): 완료 시 콜백 받을 URI
  - form 필드 `clip_orders`(선택): 업로드한 `clips`와 1:1 매칭되는 정수 순서값(중복 불가)
- `POST /api/v1/jobs/canvas/upload`: 이미지 업로드 + Canvas Job 등록
  - form 필드 `fast_mode`(선택, 기본 `false`)
  - form 필드 `animal_detection`(선택, 기본 `true`)
- `POST /api/v1/jobs/transition/upload`: 이미지 2장 업로드 + Transition Job 등록
- `POST /api/v1/jobs/last-clip/upload`: 이미지 업로드 + LastClip Job 등록
- `POST /api/v1/jobs/pipeline/upload`: 이미지들 업로드 + Pipeline Job 등록
- `GET /api/v1/jobs/output/{file_name}`: `data/output` 산출물 다운로드

콜백 payload 예시(병합 완료 시):

```json
{
  "job_id": "xxxx",
  "status": "succeeded",
  "output_path": "/abs/path/data/output/final.mp4",
  "download_uri": "http://127.0.0.1:8000/api/v1/jobs/render/output/final.mp4",
  "result_message": "final render done: ...",
  "timestamp_utc": "2026-02-19T02:10:00.000000+00:00"
}
```

주요 `stage` 예시:
- CanvasJob: `canvas_start` -> `canvas_generate` -> `canvas_validate` -> `canvas_done`
- TransitionJob: `transition_start` -> `transition_generate` -> `transition_validate` -> `transition_done`
- LastClipJob: `last_clip_start` -> `last_clip_generate` -> `last_clip_finalize` -> `last_clip_done`
- RenderJob: `render_start` -> `render_concat` -> `render_finalize` -> `render_done`
- PipelineJob: `pipeline_prepare` -> `canvas_start/canvas/canvas_done` -> `transition_start/transition/transition_done` -> `last_clip_start/last_clip_done` -> `render_start/render_done` -> `completed`

## 12. 다음 구현 권장

- 품질게이트 임계값과 타임아웃 정책 확정
- 전환/렌더 단계의 품질게이트 지표 고도화
