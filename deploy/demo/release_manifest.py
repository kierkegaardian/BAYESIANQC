#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_lock(release: Path) -> dict[str, Any]:
    lock_path = release / "deploy/demo/image-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise SystemExit("unsupported image-lock schema")
    for group in ("build_bases", "runtime_images"):
        values = lock.get(group)
        if not isinstance(values, dict) or not values:
            raise SystemExit(f"image-lock is missing {group}")
        for name, reference in values.items():
            if not isinstance(reference, str) or "@sha256:" not in reference:
                raise SystemExit(f"{group}.{name} is not pinned by digest")
    return lock


def _validate_declared_refs(release: Path, lock: dict[str, Any]) -> None:
    expected_locations = {
        lock["build_bases"]["python"]: "deploy/demo/Dockerfile.api",
        lock["build_bases"]["node"]: "deploy/demo/Dockerfile.web",
        lock["build_bases"]["nginx"]: "deploy/demo/Dockerfile.web",
        lock["runtime_images"]["postgres"]: "deploy/demo/docker-compose.yml",
        lock["runtime_images"]["caddy"]: "deploy/demo/docker-compose.yml",
        lock["runtime_images"]["cloudflared"]: "deploy/demo/compose.quick-tunnel.yml",
    }
    for reference, relative_path in expected_locations.items():
        content = (release / relative_path).read_text(encoding="utf-8")
        if reference not in content:
            raise SystemExit(f"locked reference is absent from {relative_path}: {reference}")


def _inspect_images(references: list[str]) -> list[dict[str, Any]]:
    output = subprocess.check_output(
        ["docker", "image", "inspect", *references],
        text=True,
    )
    items = json.loads(output)
    if not isinstance(items, list) or len(items) != len(references):
        raise SystemExit("docker image inspect returned an unexpected result count")
    return items


def _validate_runtime_digest(reference: str, item: dict[str, Any]) -> None:
    expected_digest = reference.rsplit("@", 1)[1]
    repo_digests = item.get("RepoDigests") or []
    if not any(value.endswith(f"@{expected_digest}") for value in repo_digests):
        raise SystemExit(
            f"runtime image does not match its locked digest: {reference}; "
            f"observed={repo_digests}"
        )


def write_manifest(release: Path, archive_sha256: str) -> None:
    lock = _read_lock(release)
    _validate_declared_refs(release, lock)
    release_sha = release.name
    built_refs = [
        f"bayesianqc-josh-demo-api:{release_sha}",
        f"bayesianqc-josh-demo-web:{release_sha}",
    ]
    runtime_entries = list(lock["runtime_images"].items())
    runtime_refs = [reference for _, reference in runtime_entries]
    inspected = _inspect_images([*built_refs, *runtime_refs])
    built_items = inspected[: len(built_refs)]
    runtime_items = inspected[len(built_refs) :]
    for (_, reference), item in zip(runtime_entries, runtime_items, strict=True):
        _validate_runtime_digest(reference, item)

    input_paths = [
        "deploy/demo/Dockerfile.api",
        "deploy/demo/Dockerfile.web",
        "deploy/demo/docker-compose.yml",
        "deploy/demo/compose.quick-tunnel.yml",
        "deploy/demo/Caddyfile.quick-tunnel",
        "deploy/demo/nginx.conf",
        "deploy/demo/image-lock.json",
    ]
    manifest = {
        "archive_sha256": archive_sha256,
        "build_bases": lock["build_bases"],
        "build_inputs_sha256": {
            relative_path: _sha256(release / relative_path) for relative_path in input_paths
        },
        "built_images": [
            {
                "id": item["Id"],
                "reference": reference,
                "repo_digests": item.get("RepoDigests") or [],
            }
            for reference, item in zip(built_refs, built_items, strict=True)
        ],
        "compose_project": "bayesianqc-josh-demo",
        "release_sha": release_sha,
        "runtime_images": [
            {
                "id": item["Id"],
                "reference": reference,
                "repo_digests": item.get("RepoDigests") or [],
                "service": service,
            }
            for (service, reference), item in zip(runtime_entries, runtime_items, strict=True)
        ],
    }
    destination = release / "RELEASE_MANIFEST.json"
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-fA-F]{64}", args.archive_sha256) is None:
        raise SystemExit("archive SHA-256 must be 64 hexadecimal characters")
    write_manifest(args.release.resolve(), args.archive_sha256.lower())


if __name__ == "__main__":
    main()
