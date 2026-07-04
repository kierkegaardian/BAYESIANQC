from __future__ import annotations

import multiprocessing
from multiprocessing.queues import Queue
from queue import Empty
from typing import Any

from fastapi import HTTPException
from app.import_db_models import ParserProfile
from app.services.import_readers import SourceRow, read_source_rows


class ImportParseTimeout(RuntimeError):
    pass


def _process_context() -> Any:
    return multiprocessing.get_context("spawn")


def _parse_worker(queue: Queue[Any], data: bytes, filename: str, profile_data: dict[str, Any]) -> None:
    profile = ParserProfile(**profile_data)
    try:
        queue.put(("ok", read_source_rows(data, filename, profile)))
    except HTTPException as exc:
        queue.put(("http_error", exc.status_code, exc.detail))
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        queue.put(("error", repr(exc)))


def read_source_rows_with_timeout(
    data: bytes,
    filename: str,
    profile: ParserProfile,
    timeout_seconds: float,
) -> list[SourceRow]:
    context = _process_context()
    queue: Queue[Any] = context.Queue(maxsize=1)
    process = context.Process(target=_parse_worker, args=(queue, data, filename, profile.model_dump()))
    process.start()
    try:
        status, *payload = queue.get(timeout=timeout_seconds)
    except Empty:
        process.terminate()
        process.join()
        raise ImportParseTimeout(
            f"Import parsing exceeded configured timeout of {timeout_seconds:g} seconds"
        )
    process.join(timeout=1)
    if process.is_alive():
        process.terminate()
        process.join()
    if status == "ok":
        return payload[0]
    if status == "http_error":
        raise HTTPException(status_code=payload[0], detail=payload[1])
    raise HTTPException(status_code=500, detail=f"Import parser worker failed: {payload[0]}")
