#!/usr/bin/env python3
from __future__ import annotations

import argparse

from sqlmodel import Session, select

from app.db import get_engine, init_db
from app.db_models import QCRecord
from app.evaluations import apply_stream_reprocessing, preview_stream_evaluations


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute and persist QCRecord evaluations for charts.")
    parser.add_argument("--stream-id", help="Reprocess only this stream_id. If omitted, reprocesses all streams.")
    parser.add_argument(
        "--reason",
        required=True,
        help="Nonblank audit reason recorded for each applied evaluation run.",
    )
    args = parser.parse_args()

    init_db()
    engine = get_engine()
    with Session(engine) as session:
        if args.stream_id:
            stream_ids = [args.stream_id]
        else:
            stream_ids = list(session.exec(select(QCRecord.stream_id).distinct()).all())
        for stream_id in stream_ids:
            print(f"[reprocess] stream_id={stream_id}")
            preview = preview_stream_evaluations(session, stream_id)
            apply_stream_reprocessing(
                session,
                stream_id,
                preview_fingerprint=preview.preview_fingerprint,
                actor="evaluation-reprocess-cli",
                reason=args.reason,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
