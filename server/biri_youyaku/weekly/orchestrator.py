from __future__ import annotations

import asyncio
import json
import logging
import uuid

from biri_youyaku.config import settings
from biri_youyaku.jobs import repo as jobs_repo
from biri_youyaku.jobs import runner
from biri_youyaku.jobs.model import JobOptions
from biri_youyaku.modules._http import openai_client
from biri_youyaku.modules.llm.client import complete, resolve_temperature
from biri_youyaku.modules.llm.usage import make_context
from biri_youyaku.weekly import repo

logger = logging.getLogger(__name__)
_tasks: dict[str, asyncio.Task[None]] = {}
_task_tokens: dict[str, str] = {}
_stopping = False


def _prompt(sources: list) -> str:
    records = []
    for job in sources:
        records.append(
            {
                "job_id": job.id,
                "title": job.title or job.id,
                "author": job.author or "",
                "summary": jobs_repo.read_summary(job),
            }
        )
    return (
        "基于以下本周视频总结，写一份简短的中文周总结。只能依据输入内容，不要引入外部事实。\n"
        '只输出严格 JSON：{"summary":"Markdown 周总结","references":[{"job_id":"输入中的 ID"}]}。\n'
        "references 最多 5 条，只能使用输入 job_id；不要输出 URL、标题或其他字段。\n\n"
        + json.dumps(records, ensure_ascii=False)
    )


def _parse(content: str, allowed_ids: set[str]) -> tuple[str, list[str]]:
    payload = json.loads(content)
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), str):
        raise ValueError("周总结模型输出必须包含 summary 字符串")
    raw_refs = payload.get("references", [])
    if not isinstance(raw_refs, list):
        raise ValueError("周总结 references 必须是数组")
    if len(raw_refs) > 5:
        raise ValueError("周总结 references 最多 5 条")
    ids: list[str] = []
    for raw in raw_refs:
        job_id = raw.get("job_id") if isinstance(raw, dict) else raw
        if not isinstance(job_id, str) or job_id not in allowed_ids:
            raise ValueError("周总结包含不允许的引用")
        if job_id not in ids:
            ids.append(job_id)
    return payload["summary"].strip(), ids


async def _run(
    week_start: str, sources: list, fingerprint_value: str, generation_token: str
) -> None:
    try:
        api_key = settings.llm_api_key
        if not api_key:
            raise RuntimeError("LLM_API_KEY 未配置")
        options = JobOptions.from_settings(settings)
        client = openai_client(
            api_key=api_key,
            base_url=options.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        context = make_context(
            job_id=None,
            operation="weekly_summary",
            base_url=options.llm_base_url,
            api_key=api_key,
            model=options.llm_model,
        )
        async with runner._summary_semaphore:
            # Queued work may have outlived its lease and been taken over by another
            # process. Verify/renew immediately before the billable request.
            if not repo.renew_generation_lease(week_start, generation_token):
                return
            raw = await complete(
                client,
                model=options.llm_model,
                messages=[{"role": "user", "content": _prompt(sources)}],
                temperature=resolve_temperature(),
                usage_context=context,
            )
        content, ref_ids = _parse(raw, {job.id for job in sources})
        # A source can be deleted or re-summarized while the LLM is running. Never revive
        # the old snapshot after that mutation; the user must explicitly refresh it.
        _, _, current_fingerprint = repo.state_for_week(week_start)
        if current_fingerprint != fingerprint_value:
            repo.mark_stale(week_start, generation_token=generation_token)
            return
        source_by_id = {job.id: job for job in sources}
        references = [
            {
                "job_id": job_id,
                "title": source_by_id[job_id].title or job_id,
                "author": source_by_id[job_id].author,
                "url": f"/jobs/{job_id}",
            }
            for job_id in ref_ids
        ]
        repo.save_completed(
            week_start,
            fingerprint_value=fingerprint_value,
            sources=sources,
            content=content,
            references=references,
            generation_token=generation_token,
        )
    except asyncio.CancelledError:
        # Service shutdown is not a failed generation. shutdown() marks this lease stale.
        raise
    except Exception as exc:
        logger.warning("Weekly summary generation failed for %s", week_start, exc_info=True)
        # Deletion/source changes win over a late generation failure.
        if (stored := repo.get(week_start)) is None or stored.status != "STALE":
            repo.save_failed(week_start, str(exc), generation_token=generation_token)
    finally:
        task = asyncio.current_task()
        if _tasks.get(week_start) is task:
            _tasks.pop(week_start, None)
            _task_tokens.pop(week_start, None)


def prepare_startup() -> None:
    global _stopping
    _stopping = False


def begin_shutdown() -> None:
    global _stopping
    _stopping = True


async def shutdown() -> None:
    """Cancel in-memory work and release only this process's leases for immediate retry."""
    begin_shutdown()
    task_items = list(_tasks.items())
    for week_start, task in task_items:
        repo.mark_stale(week_start, generation_token=_task_tokens.get(week_start))
        task.cancel()
    tasks = [task for _, task in task_items]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for week_start, task in list(_tasks.items()):
        if task.done():
            _tasks.pop(week_start, None)
            _task_tokens.pop(week_start, None)


def request_generation(week_start: str, *, refresh: bool = False) -> bool:
    if _stopping:
        return False
    active_task = _tasks.get(week_start)
    if active_task is not None and not active_task.done():
        return False
    if active_task is not None:
        _tasks.pop(week_start, None)
    stored, sources, fingerprint_value = repo.state_for_week(week_start)
    if not sources:
        repo.save_empty(week_start, fingerprint_value=fingerprint_value)
        return False
    if stored and stored.status == "COMPLETED" and not refresh:
        return False
    generation_token = uuid.uuid4().hex
    if not repo.begin_generation(
        week_start,
        fingerprint_value=fingerprint_value,
        generation_token=generation_token,
        sources=sources,
    ):
        return False
    task = asyncio.create_task(_run(week_start, sources, fingerprint_value, generation_token))
    _tasks[week_start] = task
    _task_tokens[week_start] = generation_token
    return True
