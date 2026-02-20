import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.models import JobStatus
from app.security.path_guard import ensure_safe_input_path, ensure_safe_output_path
from app.schemas import (
    CanvasUploadEnqueueResponse,
    CanvasJobCreateRequest,
    JobCancelResponse,
    JobCreateRequest,
    JobEnqueueResponse,
    LastClipUploadEnqueueResponse,
    JobResponse,
    JobRuntimeResponse,
    LastClipJobCreateRequest,
    PipelineJobCreateRequest,
    PipelineUploadEnqueueResponse,
    RenderUploadEnqueueResponse,
    RenderJobCreateRequest,
    TransitionUploadEnqueueResponse,
    TransitionJobCreateRequest,
)
from app.tasks import (
    run_canvas_render,
    run_final_render,
    run_last_clip_render,
    run_pipeline_render,
    run_test_render,
    run_transition_render,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _build_job_response(job_id: str, db: Session) -> JobResponse:
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    runtime = crud.get_job_runtime(db, job_id)
    return JobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        error_message=job.error_message,
        result_message=job.result_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        stage=runtime.stage if runtime else None,
        progress_percent=runtime.progress_percent if runtime else None,
        detail_message=runtime.detail_message if runtime else None,
        cancel_requested=runtime.cancel_requested if runtime else None,
    )


def _safe_filename(raw_name: str, default_name: str) -> str:
    base = Path(raw_name).name.strip()
    if not base:
        base = default_name
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def _normalize_callback_uri(callback_uri: str | None) -> str | None:
    if callback_uri is None:
        return None
    uri = callback_uri.strip()
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="callback_uri must be a valid http(s) URI")
    return uri


def _apply_clip_orders(clip_paths: list[str], clip_orders: list[int] | None) -> tuple[list[str], list[int]]:
    if not clip_paths:
        raise HTTPException(status_code=400, detail="clip_paths must not be empty")

    if clip_orders is None:
        default_orders = list(range(1, len(clip_paths) + 1))
        return clip_paths, default_orders

    if len(clip_orders) != len(clip_paths):
        raise HTTPException(status_code=400, detail="clip_orders length must match clip_paths/clips length")
    if any(order < 1 for order in clip_orders):
        raise HTTPException(status_code=400, detail="clip_orders must be positive integers")
    if len(set(clip_orders)) != len(clip_orders):
        raise HTTPException(status_code=400, detail="clip_orders must be unique")

    indexed = list(zip(clip_orders, range(len(clip_paths)), clip_paths))
    indexed.sort(key=lambda item: (item[0], item[1]))
    ordered_paths = [path for _, _, path in indexed]
    ordered_values = [order for order, _, _ in indexed]
    return ordered_paths, ordered_values


def _normalize_output_name(file_name: str, *, default_ext: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix:
        return file_name if suffix == default_ext else f"{Path(file_name).stem}{default_ext}"
    return f"{file_name}{default_ext}"


def _build_simple_upload_ui(*, title: str, description: str, form_inner_html: str, submit_script: str) -> HTMLResponse:
    html = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>
    :root { --bg: #f6f8fc; --card: #ffffff; --text: #1f2937; --muted: #6b7280; --line: #d1d5db; --btn: #0f766e; --btnText: #ffffff; --err: #b91c1c; }
    body { margin: 0; font-family: "Segoe UI", "Malgun Gothic", sans-serif; color: var(--text); background: radial-gradient(circle at 10% 10%, #e2e8f0 0, #f6f8fc 45%, #eef2ff 100%); }
    .wrap { max-width: 920px; margin: 40px auto; padding: 0 16px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 20px; box-shadow: 0 8px 20px rgba(15, 23, 42, .08); }
    h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: -0.01em; }
    p { margin: 0 0 18px; color: var(--muted); }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .row { display: flex; flex-direction: column; gap: 8px; }
    label { font-size: 14px; font-weight: 600; }
    input[type="text"], input[type="number"], input[type="file"], select, textarea { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; font-size: 14px; }
    textarea { resize: vertical; min-height: 88px; }
    .full { grid-column: 1 / -1; }
    button { margin-top: 14px; border: 0; border-radius: 10px; background: var(--btn); color: var(--btnText); padding: 12px 14px; font-size: 15px; font-weight: 700; cursor: pointer; }
    .muted { color: var(--muted); font-size: 13px; }
    .state { margin-top: 16px; border: 1px dashed var(--line); border-radius: 12px; padding: 12px; background: #f8fafc; white-space: pre-wrap; word-break: break-word; }
    .error { color: var(--err); font-weight: 700; }
    .top-links { margin-top: 8px; font-size: 13px; }
    .top-links a { color: #0f766e; text-decoration: none; }
    .top-links a + a::before { content: " | "; color: #94a3b8; margin: 0 6px; }
    @media (max-width: 740px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>__TITLE__</h1>
      <p>__DESCRIPTION__</p>
      <div class="top-links">
        <a href="/api/v1/jobs/upload-ui">업로드 도구 홈</a>
        <a href="/api/v1/jobs/render/upload-ui">동영상 병합</a>
      </div>
      <div class="grid">
__FORM__
      </div>
      <button id="submitBtn" type="button">요청</button>
      <div id="state" class="state">대기 중</div>
    </div>
  </div>

  <script>
    const stateEl = document.getElementById("state");
    const btn = document.getElementById("submitBtn");

    function setState(text, isError = false) {
      stateEl.textContent = text;
      stateEl.classList.toggle("error", isError);
    }

    async function pollJob(jobId, outputPath) {
      for (;;) {
        const res = await fetch(`/api/v1/jobs/${jobId}`);
        if (!res.ok) {
          setState(`Job 조회 실패 (${res.status})`, true);
          return;
        }
        const data = await res.json();
        setState(JSON.stringify(data, null, 2));
        if (data.status === "succeeded") {
          if (outputPath) {
            const name = outputPath.split("/").pop();
            const dl = document.createElement("a");
            dl.href = `/api/v1/jobs/output/${encodeURIComponent(name)}`;
            dl.textContent = `다운로드: ${name}`;
            dl.style.display = "block";
            dl.style.marginTop = "8px";
            dl.style.fontWeight = "700";
            stateEl.appendChild(dl);
          }
          return;
        }
        if (data.status === "failed") {
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }

__SUBMIT_SCRIPT__
  </script>
</body>
</html>
"""
    html = html.replace("__TITLE__", title)
    html = html.replace("__DESCRIPTION__", description)
    html = html.replace("__FORM__", form_inner_html)
    html = html.replace("__SUBMIT_SCRIPT__", submit_script)
    return HTMLResponse(content=html)


@router.post("/test", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_test_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    job = crud.create_job(db, job_type=payload.job_type)

    try:
        async_result = run_test_render.delay(job.id)
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/canvas", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_canvas_job(
    payload: CanvasJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    try:
        input_path = ensure_safe_input_path(payload.input_path)
        output_path = ensure_safe_output_path(payload.output_path)
    except Exception as exc:  # noqa: BLE001 - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = crud.create_job(db, job_type="canvas")

    try:
        async_result = run_canvas_render.delay(
            job.id,
            input_path,
            output_path,
            payload.fast_mode,
            payload.animal_detection,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/transition", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_transition_job(
    payload: TransitionJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    try:
        image_a_path = ensure_safe_input_path(payload.image_a_path)
        image_b_path = ensure_safe_input_path(payload.image_b_path)
        output_path = ensure_safe_output_path(payload.output_path)
    except Exception as exc:  # noqa: BLE001 - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = crud.create_job(db, job_type="transition")

    try:
        async_result = run_transition_render.delay(
            job.id,
            image_a_path,
            image_b_path,
            output_path,
            payload.duration_seconds,
            payload.prompt,
            payload.negative_prompt,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/last-clip", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_last_clip_job(
    payload: LastClipJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    try:
        image_path = ensure_safe_input_path(payload.image_path)
        output_path = ensure_safe_output_path(payload.output_path)
    except Exception as exc:  # noqa: BLE001 - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = crud.create_job(db, job_type="last_clip")

    try:
        async_result = run_last_clip_render.delay(
            job.id,
            image_path,
            output_path,
            payload.duration_seconds,
            payload.motion_style,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/render", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_render_job(
    payload: RenderJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    try:
        clip_paths = [ensure_safe_input_path(p) for p in payload.clip_paths]
        clip_paths, _ = _apply_clip_orders(clip_paths, payload.clip_orders)
        output_path = ensure_safe_output_path(payload.output_path)
        bgm_path = ensure_safe_input_path(payload.bgm_path) if payload.bgm_path else None
        callback_uri = _normalize_callback_uri(payload.callback_uri)
    except Exception as exc:  # noqa: BLE001 - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = crud.create_job(db, job_type="render")

    try:
        async_result = run_final_render.delay(
            job.id,
            clip_paths,
            output_path,
            bgm_path,
            payload.bgm_volume,
            callback_uri,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.get("/render/upload-ui", response_class=HTMLResponse, include_in_schema=False)
def render_upload_ui() -> HTMLResponse:
    html = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemorialTube Video Merge</title>
  <style>
    :root { --bg: #f6f8fc; --card: #ffffff; --text: #1f2937; --muted: #6b7280; --line: #d1d5db; --btn: #0f766e; --btnText: #ffffff; --err: #b91c1c; }
    body { margin: 0; font-family: "Segoe UI", "Malgun Gothic", sans-serif; color: var(--text); background: radial-gradient(circle at 10% 10%, #e2e8f0 0, #f6f8fc 45%, #eef2ff 100%); }
    .wrap { max-width: 920px; margin: 40px auto; padding: 0 16px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 20px; box-shadow: 0 8px 20px rgba(15, 23, 42, .08); }
    h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: -0.01em; }
    p { margin: 0 0 18px; color: var(--muted); }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .row { display: flex; flex-direction: column; gap: 8px; }
    label { font-size: 14px; font-weight: 600; }
    input[type="text"], input[type="number"], input[type="file"] { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; font-size: 14px; }
    .full { grid-column: 1 / -1; }
    button { margin-top: 14px; border: 0; border-radius: 10px; background: var(--btn); color: var(--btnText); padding: 12px 14px; font-size: 15px; font-weight: 700; cursor: pointer; }
    .order-table-wrap { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: #fff; }
    .order-table { width: 100%; border-collapse: collapse; }
    .order-table th, .order-table td { border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 13px; }
    .order-table th { background: #f8fafc; font-weight: 700; }
    .order-table tr:last-child td { border-bottom: 0; }
    .order-col { width: 64px; text-align: center; font-weight: 700; }
    .order-actions { width: 108px; text-align: center; white-space: nowrap; }
    .order-table tbody tr { cursor: pointer; }
    .order-table tbody tr.selected td { background: #e6fffb; }
    .order-move { margin-top: 0; width: 36px; height: 30px; padding: 0; border-radius: 8px; font-size: 16px; line-height: 1; display: none; align-items: center; justify-content: center; }
    .order-table tbody tr.selected .order-move { display: inline-flex; }
    .order-move + .order-move { margin-left: 6px; }
    .order-move:disabled { opacity: 0.45; cursor: not-allowed; }
    .muted { color: var(--muted); font-size: 13px; }
    .state { margin-top: 16px; border: 1px dashed var(--line); border-radius: 12px; padding: 12px; background: #f8fafc; white-space: pre-wrap; word-break: break-word; }
    .error { color: var(--err); font-weight: 700; }
    @media (max-width: 740px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>동영상 병합</h1>
      <p>동영상 파일을 업로드하면 하나의 영상으로 합칩니다. 요청 후 Job 상태가 자동 갱신됩니다.</p>

      <div class="grid">
        <div class="row full">
          <label for="clips">동영상 파일들 (2개 이상)</label>
          <input id="clips" type="file" accept="video/*,.mp4,.mov,.mkv,.webm,.avi,.m4v" multiple />
          <div class="muted">허용 경로 제한 때문에 업로드 API를 사용합니다.</div>
        </div>
        <div class="row full">
          <label>병합 순서</label>
          <div class="order-table-wrap">
            <table class="order-table">
              <thead>
                <tr>
                  <th class="order-col">순서</th>
                  <th>파일명</th>
                  <th class="order-actions">이동</th>
                </tr>
              </thead>
              <tbody id="clipRows">
                <tr><td colspan="3" class="muted">파일을 선택하면 순서를 지정하실 수 있습니다.</td></tr>
              </tbody>
            </table>
          </div>
          <div class="muted">로우를 선택하면 해당 로우에 화살표가 표시됩니다.</div>
        </div>
        <div class="row">
          <label for="bgm">배경음악 (선택)</label>
          <input id="bgm" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg" />
        </div>
        <div class="row">
          <label for="volume">BGM 볼륨 (0.0 ~ 1.0)</label>
          <input id="volume" type="number" min="0" max="1" step="0.05" value="0.15" />
        </div>
        <div class="row full">
          <label for="outputName">출력 파일명 (선택)</label>
          <input id="outputName" type="text" placeholder="final_merged.mp4" />
        </div>
        <div class="row full">
          <label for="callbackUri">콜백 URI (선택)</label>
          <input id="callbackUri" type="text" placeholder="https://example.com/callback" />
          <div class="muted">병합 완료 시 download_uri 포함 JSON을 POST로 전송합니다.</div>
        </div>
      </div>

      <button id="submitBtn" type="button">병합 요청</button>
      <div id="state" class="state">대기 중</div>
    </div>
  </div>

  <script>
    const stateEl = document.getElementById("state");
    const btn = document.getElementById("submitBtn");
    const clipInput = document.getElementById("clips");
    const clipRows = document.getElementById("clipRows");
    let selectedClips = [];
    let selectedIndex = -1;

    function setState(text, isError = false) {
      stateEl.textContent = text;
      stateEl.classList.toggle("error", isError);
    }

    function escapeHtml(text) {
      return text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function renderClipRows() {
      if (!selectedClips.length) {
        selectedIndex = -1;
        clipRows.innerHTML = '<tr><td colspan="3" class="muted">파일을 선택하면 순서를 지정하실 수 있습니다.</td></tr>';
        return;
      }

      clipRows.innerHTML = selectedClips.map((clip, idx) => `
        <tr data-index="${idx}" class="${idx === selectedIndex ? "selected" : ""}">
          <td class="order-col">${idx + 1}</td>
          <td>${escapeHtml(clip.name)}</td>
          <td class="order-actions">
            <button type="button" class="order-move" data-action="up" data-index="${idx}" ${idx === 0 ? "disabled" : ""}>▲</button>
            <button type="button" class="order-move" data-action="down" data-index="${idx}" ${idx === selectedClips.length - 1 ? "disabled" : ""}>▼</button>
          </td>
        </tr>
      `).join("");
    }

    function moveSelected(delta) {
      if (selectedIndex < 0 || selectedIndex >= selectedClips.length) return;
      const target = selectedIndex + delta;
      if (target < 0 || target >= selectedClips.length) return;
      [selectedClips[target], selectedClips[selectedIndex]] = [selectedClips[selectedIndex], selectedClips[target]];
      selectedIndex = target;
      renderClipRows();
    }

    clipInput.addEventListener("change", () => {
      selectedClips = Array.from(clipInput.files || []);
      selectedIndex = -1;
      renderClipRows();
    });

    clipRows.addEventListener("click", (event) => {
      const moveBtn = event.target.closest("button[data-action]");
      if (moveBtn) {
        const idx = Number(moveBtn.dataset.index);
        if (!Number.isInteger(idx) || idx < 0 || idx >= selectedClips.length) return;
        selectedIndex = idx;
        const action = moveBtn.dataset.action;
        if (action === "up") moveSelected(-1);
        if (action === "down") moveSelected(1);
        return;
      }

      const row = event.target.closest("tr[data-index]");
      if (!row) return;
      const idx = Number(row.dataset.index);
      if (!Number.isInteger(idx) || idx < 0 || idx >= selectedClips.length) return;
      selectedIndex = idx;
      renderClipRows();
    });

    async function pollJob(jobId, outputPath) {
      for (;;) {
        const res = await fetch(`/api/v1/jobs/${jobId}`);
        if (!res.ok) {
          setState(`Job 조회 실패 (${res.status})`, true);
          return;
        }
        const data = await res.json();
        setState(JSON.stringify(data, null, 2));
        if (data.status === "succeeded") {
          const name = outputPath.split("/").pop();
          const dl = document.createElement("a");
          dl.href = `/api/v1/jobs/render/output/${encodeURIComponent(name)}`;
          dl.textContent = `다운로드: ${name}`;
          dl.style.display = "block";
          dl.style.marginTop = "8px";
          dl.style.fontWeight = "700";
          stateEl.appendChild(dl);
          return;
        }
        if (data.status === "failed") {
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }

    btn.addEventListener("click", async () => {
      if (!selectedClips || selectedClips.length < 2) {
        setState("동영상 파일 2개 이상을 선택해 주세요.", true);
        return;
      }
      const bgm = document.getElementById("bgm").files[0];
      const volume = document.getElementById("volume").value || "0.15";
      const outputName = document.getElementById("outputName").value;
      const callbackUri = document.getElementById("callbackUri").value;

      const form = new FormData();
      selectedClips.forEach((clip, index) => {
        form.append("clips", clip);
        form.append("clip_orders", String(index + 1));
      });
      if (bgm) form.append("bgm", bgm);
      form.append("bgm_volume", volume);
      if (outputName) form.append("output_name", outputName);
      if (callbackUri) form.append("callback_uri", callbackUri);

      btn.disabled = true;
      setState("요청 전송 중...");
      try {
        const res = await fetch("/api/v1/jobs/render/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) {
          setState(JSON.stringify(data, null, 2), true);
          return;
        }
        setState(JSON.stringify(data, null, 2));
        await pollJob(data.job_id, data.output_path);
      } catch (err) {
        setState(String(err), true);
      } finally {
        btn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


@router.post("/render/upload", response_model=RenderUploadEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_render_upload_job(
    clips: list[UploadFile] = File(...),
    clip_orders: list[int] | None = Form(default=None),
    bgm: UploadFile | None = File(default=None),
    output_name: str | None = Form(default=None),
    bgm_volume: float = Form(default=0.15),
    callback_uri: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RenderUploadEnqueueResponse:
    if len(clips) < 2:
        raise HTTPException(status_code=400, detail="At least 2 video files are required")
    if not (0.0 <= bgm_volume <= 1.0):
        raise HTTPException(status_code=400, detail="bgm_volume must be between 0.0 and 1.0")

    callback_uri = _normalize_callback_uri(callback_uri)
    request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = Path("data/input/uploads/render_ui") / request_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[str] = []
    files_to_close: list[UploadFile] = [*clips]
    if bgm is not None:
        files_to_close.append(bgm)

    try:
        for idx, clip in enumerate(clips):
            ext = Path(clip.filename or "").suffix.lower()
            if ext not in _VIDEO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported video extension: {ext or '(none)'}",
                )
            safe_name = _safe_filename(clip.filename or "", f"clip_{idx:03d}.mp4")
            dest = upload_dir / f"{idx:03d}_{safe_name}"
            with dest.open("wb") as fp:
                shutil.copyfileobj(clip.file, fp)
            clip_paths.append(ensure_safe_input_path(str(dest)))

        clip_paths, normalized_clip_orders = _apply_clip_orders(clip_paths, clip_orders)

        bgm_path: str | None = None
        if bgm and bgm.filename:
            ext = Path(bgm.filename).suffix.lower()
            if ext not in _AUDIO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported audio extension: {ext or '(none)'}",
                )
            safe_bgm = _safe_filename(bgm.filename, "bgm.mp3")
            dest = upload_dir / f"bgm_{safe_bgm}"
            with dest.open("wb") as fp:
                shutil.copyfileobj(bgm.file, fp)
            bgm_path = ensure_safe_input_path(str(dest))

        output_file = _safe_filename(output_name or f"merged_{request_id}.mp4", f"merged_{request_id}.mp4")
        if not output_file.lower().endswith(".mp4"):
            output_file = f"{output_file}.mp4"
        output_path = ensure_safe_output_path(str(Path("data/output") / output_file))
    finally:
        for file in files_to_close:
            try:
                file.file.close()
            except Exception:
                pass

    job = crud.create_job(db, job_type="render_upload")

    try:
        async_result = run_final_render.delay(
            job.id,
            clip_paths,
            output_path,
            bgm_path,
            bgm_volume,
            callback_uri,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return RenderUploadEnqueueResponse(
        job_id=job.id,
        task_id=async_result.id,
        status=job.status,
        output_path=output_path,
        clip_count=len(clip_paths),
        clip_orders=normalized_clip_orders,
        callback_uri=callback_uri,
    )


@router.get("/upload-ui", response_class=HTMLResponse, include_in_schema=False)
def upload_ui_index() -> HTMLResponse:
    html = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemorialTube Upload Tools</title>
  <style>
    :root { --bg: #f6f8fc; --card: #ffffff; --text: #1f2937; --line: #d1d5db; --btn: #0f766e; }
    body { margin: 0; font-family: "Segoe UI", "Malgun Gothic", sans-serif; color: var(--text); background: radial-gradient(circle at 10% 10%, #e2e8f0 0, #f6f8fc 45%, #eef2ff 100%); }
    .wrap { max-width: 920px; margin: 40px auto; padding: 0 16px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 20px; box-shadow: 0 8px 20px rgba(15, 23, 42, .08); }
    h1 { margin: 0 0 8px; font-size: 28px; }
    p { margin: 0 0 16px; color: #64748b; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    a.tool { display: block; text-decoration: none; border: 1px solid var(--line); border-radius: 12px; padding: 14px; background: #fff; color: var(--text); }
    a.tool strong { display: block; color: var(--btn); margin-bottom: 6px; }
    a.tool span { font-size: 13px; color: #64748b; }
    @media (max-width: 740px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>업로드 화면 모음</h1>
      <p>기능별 업로드 화면으로 이동하실 수 있습니다.</p>
      <div class="grid">
        <a class="tool" href="/api/v1/jobs/canvas/upload-ui"><strong>Canvas</strong><span>이미지 1장을 캔버스 처리</span></a>
        <a class="tool" href="/api/v1/jobs/transition/upload-ui"><strong>Transition</strong><span>이미지 2장 전환 클립 생성</span></a>
        <a class="tool" href="/api/v1/jobs/last-clip/upload-ui"><strong>Last Clip</strong><span>마지막 단독 클립 생성</span></a>
        <a class="tool" href="/api/v1/jobs/pipeline/upload-ui"><strong>Pipeline</strong><span>전체 파이프라인 실행</span></a>
        <a class="tool" href="/api/v1/jobs/render/upload-ui"><strong>Render Merge</strong><span>동영상 병합</span></a>
      </div>
    </div>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html)


@router.get("/canvas/upload-ui", response_class=HTMLResponse, include_in_schema=False)
def canvas_upload_ui() -> HTMLResponse:
    form_inner_html = """
        <div class="row full">
          <label for="image">이미지 파일</label>
          <input id="image" type="file" accept="image/*,.jpg,.jpeg,.png,.webp" />
        </div>
        <div class="row">
          <label for="fastMode">빠른 모드</label>
          <select id="fastMode">
            <option value="false" selected>기본(품질 우선)</option>
            <option value="true">빠른 모드(steps=12)</option>
          </select>
        </div>
        <div class="row">
          <label for="animalDetection">동물 검출</label>
          <select id="animalDetection">
            <option value="true" selected>사용</option>
            <option value="false">미사용</option>
          </select>
        </div>
        <div class="row full">
          <label for="outputName">출력 파일명 (선택)</label>
          <input id="outputName" type="text" placeholder="canvas_output.jpg" />
          <div class="muted">확장자가 없거나 이미지 확장자가 아니면 `.jpg`로 저장됩니다.</div>
        </div>
"""
    submit_script = """
    btn.addEventListener("click", async () => {
      const image = document.getElementById("image").files[0];
      if (!image) {
        setState("이미지 파일을 선택해 주세요.", true);
        return;
      }
      const outputName = document.getElementById("outputName").value;
      const fastMode = document.getElementById("fastMode").value === "true";
      const animalDetection = document.getElementById("animalDetection").value === "true";
      const form = new FormData();
      form.append("image", image);
      if (outputName) form.append("output_name", outputName);
      form.append("fast_mode", String(fastMode));
      form.append("animal_detection", String(animalDetection));

      btn.disabled = true;
      setState("요청 전송 중...");
      try {
        const res = await fetch("/api/v1/jobs/canvas/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) {
          setState(JSON.stringify(data, null, 2), true);
          return;
        }
        setState(JSON.stringify(data, null, 2));
        await pollJob(data.job_id, data.output_path);
      } catch (err) {
        setState(String(err), true);
      } finally {
        btn.disabled = false;
      }
    });
"""
    return _build_simple_upload_ui(
        title="Canvas 업로드 실행",
        description="이미지 1장을 업로드해 캔버스 보정 결과를 생성합니다.",
        form_inner_html=form_inner_html,
        submit_script=submit_script,
    )


@router.post("/canvas/upload", response_model=CanvasUploadEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_canvas_upload_job(
    image: UploadFile = File(...),
    output_name: str | None = Form(default=None),
    fast_mode: bool = Form(default=False),
    animal_detection: bool = Form(default=True),
    db: Session = Depends(get_db),
) -> CanvasUploadEnqueueResponse:
    ext = Path(image.filename or "").suffix.lower()
    if ext not in _IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image extension: {ext or '(none)'}")

    request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = Path("data/input/uploads/canvas_ui") / request_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        safe_name = _safe_filename(image.filename or "", "input.jpg")
        input_dest = upload_dir / f"input_{safe_name}"
        with input_dest.open("wb") as fp:
            shutil.copyfileobj(image.file, fp)

        input_path = ensure_safe_input_path(str(input_dest))
        output_file = _safe_filename(output_name or f"canvas_{request_id}.jpg", f"canvas_{request_id}.jpg")
        output_file = _normalize_output_name(output_file, default_ext=".jpg")
        output_path = ensure_safe_output_path(str(Path("data/output") / output_file))
    finally:
        try:
            image.file.close()
        except Exception:
            pass

    job = crud.create_job(db, job_type="canvas_upload")
    try:
        async_result = run_canvas_render.delay(
            job.id,
            input_path,
            output_path,
            fast_mode,
            animal_detection,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return CanvasUploadEnqueueResponse(
        job_id=job.id,
        task_id=async_result.id,
        status=job.status,
        input_path=input_path,
        output_path=output_path,
        fast_mode=fast_mode,
        animal_detection=animal_detection,
    )


@router.get("/transition/upload-ui", response_class=HTMLResponse, include_in_schema=False)
def transition_upload_ui() -> HTMLResponse:
    form_inner_html = """
        <div class="row">
          <label for="imageA">시작 이미지</label>
          <input id="imageA" type="file" accept="image/*,.jpg,.jpeg,.png,.webp" />
        </div>
        <div class="row">
          <label for="imageB">끝 이미지</label>
          <input id="imageB" type="file" accept="image/*,.jpg,.jpeg,.png,.webp" />
        </div>
        <div class="row">
          <label for="duration">전환 길이</label>
          <select id="duration">
            <option value="6">6초</option>
            <option value="10">10초</option>
          </select>
        </div>
        <div class="row full">
          <label for="prompt">프롬프트</label>
          <textarea id="prompt" placeholder="gentle memorial cinematic transition, soft light"></textarea>
        </div>
        <div class="row full">
          <label for="negativePrompt">네거티브 프롬프트 (선택)</label>
          <textarea id="negativePrompt" placeholder="extra animal, distorted pet"></textarea>
        </div>
        <div class="row full">
          <label for="outputName">출력 파일명 (선택)</label>
          <input id="outputName" type="text" placeholder="transition_output.mp4" />
          <div class="muted">확장자가 없거나 mp4가 아니면 `.mp4`로 저장됩니다.</div>
        </div>
"""
    submit_script = """
    btn.addEventListener("click", async () => {
      const imageA = document.getElementById("imageA").files[0];
      const imageB = document.getElementById("imageB").files[0];
      const duration = document.getElementById("duration").value;
      const prompt = document.getElementById("prompt").value.trim();
      const negativePrompt = document.getElementById("negativePrompt").value;
      const outputName = document.getElementById("outputName").value;

      if (!imageA || !imageB) {
        setState("시작/끝 이미지를 모두 선택해 주세요.", true);
        return;
      }
      if (!prompt) {
        setState("프롬프트를 입력해 주세요.", true);
        return;
      }

      const form = new FormData();
      form.append("image_a", imageA);
      form.append("image_b", imageB);
      form.append("duration_seconds", duration);
      form.append("prompt", prompt);
      if (negativePrompt) form.append("negative_prompt", negativePrompt);
      if (outputName) form.append("output_name", outputName);

      btn.disabled = true;
      setState("요청 전송 중...");
      try {
        const res = await fetch("/api/v1/jobs/transition/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) {
          setState(JSON.stringify(data, null, 2), true);
          return;
        }
        setState(JSON.stringify(data, null, 2));
        await pollJob(data.job_id, data.output_path);
      } catch (err) {
        setState(String(err), true);
      } finally {
        btn.disabled = false;
      }
    });
"""
    return _build_simple_upload_ui(
        title="Transition 업로드 실행",
        description="이미지 2장을 업로드해 전환 영상을 생성합니다.",
        form_inner_html=form_inner_html,
        submit_script=submit_script,
    )


@router.post("/transition/upload", response_model=TransitionUploadEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_transition_upload_job(
    image_a: UploadFile = File(...),
    image_b: UploadFile = File(...),
    duration_seconds: int = Form(default=6),
    prompt: str = Form(...),
    negative_prompt: str | None = Form(default=None),
    output_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> TransitionUploadEnqueueResponse:
    if duration_seconds not in {6, 10}:
        raise HTTPException(status_code=400, detail="duration_seconds must be 6 or 10")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    files_to_close = [image_a, image_b]
    request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = Path("data/input/uploads/transition_ui") / request_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        ext_a = Path(image_a.filename or "").suffix.lower()
        ext_b = Path(image_b.filename or "").suffix.lower()
        if ext_a not in _IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported image extension: {ext_a or '(none)'}")
        if ext_b not in _IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported image extension: {ext_b or '(none)'}")

        safe_a = _safe_filename(image_a.filename or "", "image_a.jpg")
        safe_b = _safe_filename(image_b.filename or "", "image_b.jpg")
        dest_a = upload_dir / f"a_{safe_a}"
        dest_b = upload_dir / f"b_{safe_b}"
        with dest_a.open("wb") as fp:
            shutil.copyfileobj(image_a.file, fp)
        with dest_b.open("wb") as fp:
            shutil.copyfileobj(image_b.file, fp)

        image_a_path = ensure_safe_input_path(str(dest_a))
        image_b_path = ensure_safe_input_path(str(dest_b))
        output_file = _safe_filename(output_name or f"transition_{request_id}.mp4", f"transition_{request_id}.mp4")
        output_file = _normalize_output_name(output_file, default_ext=".mp4")
        output_path = ensure_safe_output_path(str(Path("data/output") / output_file))
    finally:
        for file in files_to_close:
            try:
                file.file.close()
            except Exception:
                pass

    job = crud.create_job(db, job_type="transition_upload")
    try:
        async_result = run_transition_render.delay(
            job.id,
            image_a_path,
            image_b_path,
            output_path,
            duration_seconds,
            prompt.strip(),
            negative_prompt.strip() if negative_prompt and negative_prompt.strip() else None,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return TransitionUploadEnqueueResponse(
        job_id=job.id,
        task_id=async_result.id,
        status=job.status,
        image_a_path=image_a_path,
        image_b_path=image_b_path,
        output_path=output_path,
        duration_seconds=duration_seconds,
    )


@router.get("/last-clip/upload-ui", response_class=HTMLResponse, include_in_schema=False)
def last_clip_upload_ui() -> HTMLResponse:
    form_inner_html = """
        <div class="row full">
          <label for="image">이미지 파일</label>
          <input id="image" type="file" accept="image/*,.jpg,.jpeg,.png,.webp" />
        </div>
        <div class="row">
          <label for="duration">길이(초)</label>
          <input id="duration" type="number" min="2" max="20" value="4" />
        </div>
        <div class="row">
          <label for="motion">모션</label>
          <select id="motion">
            <option value="zoom_in">zoom_in</option>
            <option value="zoom_out">zoom_out</option>
            <option value="none">none</option>
          </select>
        </div>
        <div class="row full">
          <label for="outputName">출력 파일명 (선택)</label>
          <input id="outputName" type="text" placeholder="last_clip_output.mp4" />
          <div class="muted">확장자가 없거나 mp4가 아니면 `.mp4`로 저장됩니다.</div>
        </div>
"""
    submit_script = """
    btn.addEventListener("click", async () => {
      const image = document.getElementById("image").files[0];
      const duration = document.getElementById("duration").value;
      const motion = document.getElementById("motion").value;
      const outputName = document.getElementById("outputName").value;

      if (!image) {
        setState("이미지 파일을 선택해 주세요.", true);
        return;
      }

      const form = new FormData();
      form.append("image", image);
      form.append("duration_seconds", duration);
      form.append("motion_style", motion);
      if (outputName) form.append("output_name", outputName);

      btn.disabled = true;
      setState("요청 전송 중...");
      try {
        const res = await fetch("/api/v1/jobs/last-clip/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) {
          setState(JSON.stringify(data, null, 2), true);
          return;
        }
        setState(JSON.stringify(data, null, 2));
        await pollJob(data.job_id, data.output_path);
      } catch (err) {
        setState(String(err), true);
      } finally {
        btn.disabled = false;
      }
    });
"""
    return _build_simple_upload_ui(
        title="Last Clip 업로드 실행",
        description="이미지 1장으로 마지막 단독 클립을 생성합니다.",
        form_inner_html=form_inner_html,
        submit_script=submit_script,
    )


@router.post("/last-clip/upload", response_model=LastClipUploadEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_last_clip_upload_job(
    image: UploadFile = File(...),
    duration_seconds: int = Form(default=4),
    motion_style: str = Form(default="zoom_in"),
    output_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> LastClipUploadEnqueueResponse:
    if not (2 <= duration_seconds <= 20):
        raise HTTPException(status_code=400, detail="duration_seconds must be between 2 and 20")
    if motion_style not in {"zoom_in", "zoom_out", "none"}:
        raise HTTPException(status_code=400, detail="motion_style must be zoom_in, zoom_out, or none")

    ext = Path(image.filename or "").suffix.lower()
    if ext not in _IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image extension: {ext or '(none)'}")

    request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = Path("data/input/uploads/last_clip_ui") / request_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        safe_name = _safe_filename(image.filename or "", "input.jpg")
        input_dest = upload_dir / f"input_{safe_name}"
        with input_dest.open("wb") as fp:
            shutil.copyfileobj(image.file, fp)

        input_path = ensure_safe_input_path(str(input_dest))
        output_file = _safe_filename(output_name or f"last_clip_{request_id}.mp4", f"last_clip_{request_id}.mp4")
        output_file = _normalize_output_name(output_file, default_ext=".mp4")
        output_path = ensure_safe_output_path(str(Path("data/output") / output_file))
    finally:
        try:
            image.file.close()
        except Exception:
            pass

    job = crud.create_job(db, job_type="last_clip_upload")
    try:
        async_result = run_last_clip_render.delay(job.id, input_path, output_path, duration_seconds, motion_style)
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return LastClipUploadEnqueueResponse(
        job_id=job.id,
        task_id=async_result.id,
        status=job.status,
        input_path=input_path,
        output_path=output_path,
        duration_seconds=duration_seconds,
        motion_style=motion_style,
    )


@router.get("/pipeline/upload-ui", response_class=HTMLResponse, include_in_schema=False)
def pipeline_upload_ui() -> HTMLResponse:
    form_inner_html = """
        <div class="row full">
          <label for="images">이미지 파일들 (1개 이상)</label>
          <input id="images" type="file" accept="image/*,.jpg,.jpeg,.png,.webp" multiple />
        </div>
        <div class="row full">
          <label for="bgm">배경음악 (선택)</label>
          <input id="bgm" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg" />
        </div>
        <div class="row">
          <label for="transitionDuration">전환 길이</label>
          <select id="transitionDuration">
            <option value="6">6초</option>
            <option value="10">10초</option>
          </select>
        </div>
        <div class="row">
          <label for="bgmVolume">BGM 볼륨 (0.0 ~ 1.0)</label>
          <input id="bgmVolume" type="number" min="0" max="1" step="0.05" value="0.15" />
        </div>
        <div class="row full">
          <label for="transitionPrompt">전환 프롬프트</label>
          <textarea id="transitionPrompt" placeholder="gentle memorial cinematic transition, soft light"></textarea>
        </div>
        <div class="row full">
          <label for="transitionNegativePrompt">전환 네거티브 프롬프트 (선택)</label>
          <textarea id="transitionNegativePrompt" placeholder="extra animal, distorted pet"></textarea>
        </div>
        <div class="row">
          <label for="lastDuration">마지막 클립 길이(초)</label>
          <input id="lastDuration" type="number" min="2" max="20" value="4" />
        </div>
        <div class="row">
          <label for="lastMotion">마지막 클립 모션</label>
          <select id="lastMotion">
            <option value="zoom_in">zoom_in</option>
            <option value="zoom_out">zoom_out</option>
            <option value="none">none</option>
          </select>
        </div>
        <div class="row full">
          <label for="outputName">최종 출력 파일명 (선택)</label>
          <input id="outputName" type="text" placeholder="pipeline_output.mp4" />
          <div class="muted">확장자가 없거나 mp4가 아니면 `.mp4`로 저장됩니다.</div>
        </div>
"""
    submit_script = """
    btn.addEventListener("click", async () => {
      const images = Array.from(document.getElementById("images").files || []);
      const bgm = document.getElementById("bgm").files[0];
      const transitionDuration = document.getElementById("transitionDuration").value;
      const transitionPrompt = document.getElementById("transitionPrompt").value.trim();
      const transitionNegativePrompt = document.getElementById("transitionNegativePrompt").value;
      const lastDuration = document.getElementById("lastDuration").value;
      const lastMotion = document.getElementById("lastMotion").value;
      const bgmVolume = document.getElementById("bgmVolume").value || "0.15";
      const outputName = document.getElementById("outputName").value;

      if (images.length < 1) {
        setState("이미지 파일을 1개 이상 선택해 주세요.", true);
        return;
      }
      if (!transitionPrompt) {
        setState("전환 프롬프트를 입력해 주세요.", true);
        return;
      }

      const form = new FormData();
      for (const image of images) form.append("images", image);
      if (bgm) form.append("bgm", bgm);
      form.append("transition_duration_seconds", transitionDuration);
      form.append("transition_prompt", transitionPrompt);
      if (transitionNegativePrompt) form.append("transition_negative_prompt", transitionNegativePrompt);
      form.append("last_clip_duration_seconds", lastDuration);
      form.append("last_clip_motion_style", lastMotion);
      form.append("bgm_volume", bgmVolume);
      if (outputName) form.append("output_name", outputName);

      btn.disabled = true;
      setState("요청 전송 중...");
      try {
        const res = await fetch("/api/v1/jobs/pipeline/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) {
          setState(JSON.stringify(data, null, 2), true);
          return;
        }
        setState(JSON.stringify(data, null, 2));
        await pollJob(data.job_id, data.output_path);
      } catch (err) {
        setState(String(err), true);
      } finally {
        btn.disabled = false;
      }
    });
"""
    return _build_simple_upload_ui(
        title="Pipeline 업로드 실행",
        description="이미지 여러 장으로 전체 파이프라인(Canvas -> Transition -> LastClip -> Render)을 실행합니다.",
        form_inner_html=form_inner_html,
        submit_script=submit_script,
    )


@router.post("/pipeline/upload", response_model=PipelineUploadEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_pipeline_upload_job(
    images: list[UploadFile] = File(...),
    bgm: UploadFile | None = File(default=None),
    transition_duration_seconds: int = Form(default=6),
    transition_prompt: str = Form(...),
    transition_negative_prompt: str | None = Form(default=None),
    last_clip_duration_seconds: int = Form(default=4),
    last_clip_motion_style: str = Form(default="zoom_in"),
    bgm_volume: float = Form(default=0.15),
    output_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> PipelineUploadEnqueueResponse:
    if len(images) < 1:
        raise HTTPException(status_code=400, detail="At least 1 image file is required")
    if transition_duration_seconds not in {6, 10}:
        raise HTTPException(status_code=400, detail="transition_duration_seconds must be 6 or 10")
    if not transition_prompt.strip():
        raise HTTPException(status_code=400, detail="transition_prompt is required")
    if not (2 <= last_clip_duration_seconds <= 20):
        raise HTTPException(status_code=400, detail="last_clip_duration_seconds must be between 2 and 20")
    if last_clip_motion_style not in {"zoom_in", "zoom_out", "none"}:
        raise HTTPException(status_code=400, detail="last_clip_motion_style must be zoom_in, zoom_out, or none")
    if not (0.0 <= bgm_volume <= 1.0):
        raise HTTPException(status_code=400, detail="bgm_volume must be between 0.0 and 1.0")

    request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    upload_dir = Path("data/input/uploads/pipeline_ui") / request_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    files_to_close: list[UploadFile] = [*images]
    if bgm is not None:
        files_to_close.append(bgm)

    try:
        for idx, image in enumerate(images):
            ext = Path(image.filename or "").suffix.lower()
            if ext not in _IMAGE_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported image extension: {ext or '(none)'}",
                )
            safe_name = _safe_filename(image.filename or "", f"image_{idx:03d}.jpg")
            dest = upload_dir / f"{idx:03d}_{safe_name}"
            with dest.open("wb") as fp:
                shutil.copyfileobj(image.file, fp)
            image_paths.append(ensure_safe_input_path(str(dest)))

        bgm_path: str | None = None
        if bgm and bgm.filename:
            ext = Path(bgm.filename).suffix.lower()
            if ext not in _AUDIO_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported audio extension: {ext or '(none)'}",
                )
            safe_bgm = _safe_filename(bgm.filename, "bgm.mp3")
            bgm_dest = upload_dir / f"bgm_{safe_bgm}"
            with bgm_dest.open("wb") as fp:
                shutil.copyfileobj(bgm.file, fp)
            bgm_path = ensure_safe_input_path(str(bgm_dest))

        working_marker = ensure_safe_output_path(str(Path("data/work/pipeline_ui") / request_id / ".path_check"))
        working_dir = str(Path(working_marker).parent)
        output_file = _safe_filename(output_name or f"pipeline_{request_id}.mp4", f"pipeline_{request_id}.mp4")
        output_file = _normalize_output_name(output_file, default_ext=".mp4")
        output_path = ensure_safe_output_path(str(Path("data/output") / output_file))
    finally:
        for file in files_to_close:
            try:
                file.file.close()
            except Exception:
                pass

    job = crud.create_job(db, job_type="pipeline_upload")
    try:
        async_result = run_pipeline_render.delay(
            job.id,
            image_paths,
            working_dir,
            output_path,
            transition_duration_seconds,
            transition_prompt.strip(),
            transition_negative_prompt.strip() if transition_negative_prompt and transition_negative_prompt.strip() else None,
            last_clip_duration_seconds,
            last_clip_motion_style,
            bgm_path,
            bgm_volume,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return PipelineUploadEnqueueResponse(
        job_id=job.id,
        task_id=async_result.id,
        status=job.status,
        image_count=len(image_paths),
        working_dir=working_dir,
        output_path=output_path,
        bgm_path=bgm_path,
    )


@router.get("/output/{file_name}", response_class=FileResponse, include_in_schema=False)
def download_output_file(file_name: str) -> FileResponse:
    safe = _safe_filename(file_name, "output.bin")
    path = ensure_safe_input_path(str(Path("data/output") / safe))
    return FileResponse(path=path, filename=Path(path).name)


@router.get("/render/output/{file_name}", response_class=FileResponse, include_in_schema=False)
def download_render_output(file_name: str) -> FileResponse:
    safe = _safe_filename(file_name, "output.mp4")
    path = ensure_safe_input_path(str(Path("data/output") / safe))
    return FileResponse(path=path, filename=Path(path).name, media_type="video/mp4")


@router.post("/pipeline", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_pipeline_job(
    payload: PipelineJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    try:
        image_paths = [ensure_safe_input_path(p) for p in payload.image_paths]
        # Validate working directory under allowed roots.
        working_marker = ensure_safe_output_path(str(Path(payload.working_dir) / ".path_check"))
        working_dir = str(Path(working_marker).parent)
        final_output_path = ensure_safe_output_path(payload.final_output_path)
        bgm_path = ensure_safe_input_path(payload.bgm_path) if payload.bgm_path else None
    except Exception as exc:  # noqa: BLE001 - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = crud.create_job(db, job_type="pipeline")

    try:
        async_result = run_pipeline_render.delay(
            job.id,
            image_paths,
            working_dir,
            final_output_path,
            payload.transition_duration_seconds,
            payload.transition_prompt,
            payload.transition_negative_prompt,
            payload.last_clip_duration_seconds,
            payload.last_clip_motion_style,
            bgm_path,
            payload.bgm_volume,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    return _build_job_response(job_id, db)


@router.get("/{job_id}/runtime", response_model=JobRuntimeResponse)
def get_job_runtime(job_id: str, db: Session = Depends(get_db)) -> JobRuntimeResponse:
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    runtime = crud.get_job_runtime(db, job_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Job runtime not found")
    return runtime


@router.get("", response_model=list[JobResponse])
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[JobResponse]:
    jobs = crud.list_jobs(db, limit=limit)
    runtimes = crud.list_job_runtimes(db, [j.id for j in jobs])
    responses: list[JobResponse] = []
    for job in jobs:
        rt = runtimes.get(job.id)
        responses.append(
            JobResponse(
                id=job.id,
                job_type=job.job_type,
                status=job.status,
                error_message=job.error_message,
                result_message=job.result_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
                stage=rt.stage if rt else None,
                progress_percent=rt.progress_percent if rt else None,
                detail_message=rt.detail_message if rt else None,
                cancel_requested=rt.cancel_requested if rt else None,
            )
        )
    return responses


@router.post("/{job_id}/cancel", response_model=JobCancelResponse, status_code=status.HTTP_202_ACCEPTED)
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> JobCancelResponse:
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
        runtime = crud.get_job_runtime(db, job_id)
        return JobCancelResponse(
            job_id=job.id,
            status=job.status,
            cancel_requested=bool(runtime.cancel_requested) if runtime else False,
            stage=runtime.stage if runtime else "unknown",
            progress_percent=runtime.progress_percent if runtime else 0,
            detail_message=runtime.detail_message if runtime else "already finished",
        )

    runtime = crud.request_job_cancel(db, job_id)
    return JobCancelResponse(
        job_id=job.id,
        status=job.status,
        cancel_requested=runtime.cancel_requested,
        stage=runtime.stage,
        progress_percent=runtime.progress_percent,
        detail_message=runtime.detail_message,
    )
