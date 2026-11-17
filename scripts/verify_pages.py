"""Verify that the public Pages release matches the local public build."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

import httpx

ROOT = Path(__file__).resolve().parents[1]


def verify(url, expected, sha):
    files = [
        expected / "index.html",
        *sorted((expected / "assets").glob("*.js")),
        *sorted((expected / "assets").glob("*.css")),
    ]
    for name in (
        "static/icons/camera.png",
        "static/icons/camera-white.png",
        "static/icons/history.png",
        "static/crops/wheat.png",
    ):
        candidate = expected / name
        if candidate.is_file():
            files.append(candidate)
    items = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for path in files:
            relative = path.relative_to(expected).as_posix()
            target = urljoin(url.rstrip("/") + "/", relative)
            response = client.get(
                target, params={"v": sha[:12]} if relative == "index.html" else None
            )
            local = hashlib.sha256(path.read_bytes()).hexdigest()
            remote = hashlib.sha256(response.content).hexdigest()
            items.append(
                {
                    "path": relative,
                    "status": response.status_code,
                    "bytes": len(response.content),
                    "sha256": local,
                    "matches": response.status_code == 200 and local == remote,
                }
            )
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "commit": sha,
        "url": url,
        "index_cache_busted": True,
        "passed": all(item["matches"] for item in items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url", default="https://chenzhihao-dev.github.io/AgriVision-system/"
    )
    parser.add_argument(
        "--expected", type=Path, default=ROOT / "apps/client/dist/pages"
    )
    parser.add_argument("--sha", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.url, args.expected, args.sha)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "checked": len(report["items"]),
                "mismatches": [
                    item["path"] for item in report["items"] if not item["matches"]
                ],
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)
