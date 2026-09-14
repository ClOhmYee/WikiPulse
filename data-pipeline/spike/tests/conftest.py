"""Spark 가 워커로 띄울 파이썬을 현재 인터프리터로 고정한다.

`data-pipeline/tests/conftest.py` 와 같은 내용이다. spike 는 자체 pytest.ini 를 써서
rootdir 이 spike/ 가 되고, 그 바깥 conftest 는 로드되지 않는다 — 그래서 여기에도 둔다.

⚠️ 이걸 안 걸면 Windows 에서 executor 가 시스템 PATH 의 python 을 찾다가
   "CreateProcess error=2" 로 죽는다. 스택트레이스에 파이썬 얘기가 없어서
   **파이썬 버전 문제로 오진하기 쉽다** (2026-09-14 실제로 그렇게 오진했다 —
   venv 는 3.11 이라 PySpark 3.5 지원 범위 안이고, 원인은 워커 경로였다).
"""

from __future__ import annotations

import os
import sys
import warnings

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

# PySpark 3.5 지원 범위는 3.8~3.11. 그보다 높으면 워커가 죽는다.
if sys.version_info >= (3, 12):
    warnings.warn(
        f"Python {sys.version_info.major}.{sys.version_info.minor} 에서는 "
        "PySpark 3.5 워커가 죽는다 (지원 범위 3.8~3.11). venv 를 3.11 로 만들 것.",
        RuntimeWarning,
        stacklevel=1,
    )
