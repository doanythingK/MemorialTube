# MemorialTube Java

이 모듈은 `Python`을 호출하지 않는 `Spring Boot` 단독 실행 구현입니다.

현재 Java가 직접 수행하는 범위:
- `GET /api/v1/health`
- `POST /api/v1/jobs/test`
- `POST /api/v1/jobs/canvas`
- `POST /api/v1/jobs/transition`
- `POST /api/v1/jobs/last-clip`
- `POST /api/v1/jobs/render`
- `POST /api/v1/jobs/pipeline`
- `GET /api/v1/jobs/{jobId}`
- `GET /api/v1/jobs/{jobId}/runtime`
- `POST /api/v1/jobs/{jobId}/cancel`
- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{projectId}`
- `POST /api/v1/projects/{projectId}/assets`
- `GET /api/v1/projects/{projectId}/assets`
- `POST /api/v1/projects/{projectId}/run`
- `POST /api/v1/projects/{projectId}/cancel`

구현 방식:
- 저장소: `H2(file)` + `Spring Data JPA`
- 비동기 Job 실행: `ThreadPoolTaskExecutor`
- 캔버스 생성: Java 이미지 처리 기반 안전 배경 확장
- 전환 생성: Java 내부 모션/블렌드 기반 전환
- 마지막 클립/최종 렌더: `FFmpeg`

현재 제한:
- Python `diffusers/torch` 생성형 모델을 Java 런타임으로 직접 옮기지는 않았습니다.
- 따라서 Java 전환/캔버스 품질은 Python 생성형 경로와 동일하지 않습니다.
- 현재 Java 구현은 `단독 실행 가능한 병행 파이프라인`을 우선 만든 상태입니다.

전제:
- JDK 21+
- Gradle 8+
- FFmpeg

실행:

```bash
cd spring-api
gradle bootRun
```

또는 저장소 루트에서:

```bash
./scripts/start_spring_api.sh
```

Windows에서는:

```bat
start_memorialtube_java.bat
```

기본 포트:
- `http://127.0.0.1:8080`
