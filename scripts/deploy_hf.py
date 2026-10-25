#!/usr/bin/env python
"""Deploy the full stack to a Hugging Face Space (single container).

Usage:
    pip install huggingface_hub
    python scripts/deploy_hf.py \
        --username YOUR_HF_NAME \
        --space-name date-palm-health-monitor \
        --token-file data/hf_token.txt \
        --database-url-file data/neon_url.txt \
        [--glm-api-key-file data/glm_key.txt]

Token file: a Hugging Face access token with WRITE permission
(huggingface.co/settings/tokens).
Database URL file: the Neon (or any managed Postgres) connection string,
e.g. postgres://user:pass@ep-xxx.neon.tech/neondb?sslmode=require

The script:
  1. assembles a clean Space repo (app code + hf-space configs + README
     frontmatter) in a temp directory,
  2. creates the Docker Space if needed,
  3. sets the Space secrets (DATABASE_URL, SECRET_KEY, GLM_API_KEY,
     STREAMLIT_API_URL),
  4. uploads everything and prints the public URL.
"""

from __future__ import annotations

import argparse
import secrets as pysecrets
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SPACE_README = """---
title: Date Palm Health Monitor
emoji: "\\U0001F334"
colorFrom: green
colorTo: brown
sdk: docker
app_port: 7860
pinned: false
---

Date Palm Health Monitor — AI-powered disease detection for date palms
(Red Palm Weevil, fungal infections) with GPS tree registry, inspection
history and treatment recommendations. FastAPI + Streamlit + PostgreSQL
behind nginx in one container.
"""

#: (source, destination) — app code + configs copied into the Space repo.
PAYLOAD = [
    ("backend", "backend"),
    ("frontend", "frontend"),
    ("migrations", "migrations"),
    ("ml", "ml"),
    ("scripts/create_admin.py", "scripts/create_admin.py"),
    ("requirements.txt", "requirements.txt"),
    ("alembic.ini", "alembic.ini"),
    ("hf-space/Dockerfile.hf", "Dockerfile"),
    ("hf-space/hf-entrypoint.sh", "hf-entrypoint.sh"),
    ("hf-space/nginx.conf", "nginx.conf"),
    ("hf-space/supervisord.conf", "supervisord.conf"),
]

IGNORED_SUFFIXES = {".pyc"}


def read_secret_file(path: Path, label: str) -> str:
    if not path.is_file():
        raise SystemExit(f"{label} file not found: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SystemExit(f"{label} file is empty: {path}")
    return value


def build_payload_dir(target: Path) -> None:
    for source_name, dest_name in PAYLOAD:
        source = PROJECT_ROOT / source_name
        dest = target / dest_name
        if source.is_dir():
            shutil.copytree(
                source,
                dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    (target / "README.md").write_text(SPACE_README, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="your HF username")
    parser.add_argument("--space-name", default="date-palm-health-monitor")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--database-url-file", type=Path, required=True)
    parser.add_argument("--glm-api-key-file", type=Path, default=None)
    args = parser.parse_args()

    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit("huggingface_hub not installed: pip install huggingface_hub")

    token = read_secret_file(args.token_file, "HF token")
    database_url = read_secret_file(args.database_url_file, "Database URL")
    glm_key = (
        read_secret_file(args.glm_api_key_file, "GLM API key")
        if args.glm_api_key_file
        else ""
    )

    repo_id = f"{args.username}/{args.space_name}"
    space_url = f"https://{args.username}-{args.space_name}.hf.space"
    secret_key = pysecrets.token_urlsafe(64)

    api = HfApi(token=token)
    print(f"[deploy] creating Space {repo_id} (idempotent)...")
    api.create_repo(
        repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True
    )

    print("[deploy] setting Space secrets...")
    for key, value in [
        ("DATABASE_URL", database_url),
        ("SECRET_KEY", secret_key),
        ("GLM_API_KEY", glm_key),
        ("ENVIRONMENT", "production"),
        ("DEBUG", "false"),
        ("STREAMLIT_API_URL", space_url),
    ]:
        api.add_space_secret(repo_id=repo_id, key=key, value=value)

    with tempfile.TemporaryDirectory(prefix="hf_space_") as tmp:
        payload = Path(tmp) / "space"
        payload.mkdir()
        print("[deploy] assembling Space payload...")
        build_payload_dir(payload)
        print("[deploy] uploading (this creates a commit and starts the build)...")
        api.upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=str(payload),
            commit_message="Deploy Date Palm Health Monitor",
        )

    print()
    print(f"Space repo : https://huggingface.co/spaces/{repo_id}")
    print(f"Public URL : {space_url}")
    print("Build takes ~5-10 min — watch it at the Space page (Logs tab).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
