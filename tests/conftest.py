from __future__ import annotations

import os

os.environ.setdefault("POSTGRES_DSN", "postgresql://aigateway:aigateway@localhost:5432/aigateway")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SERVICE_NAME", "gateway")
