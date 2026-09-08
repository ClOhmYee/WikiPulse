"""Spark 가 워커로 띄울 파이썬을 현재 인터프리터로 고정한다.

이걸 안 하면 Windows 에서 executor 가 시스템 PATH 의 python 을 찾다가
"Python worker exited unexpectedly (crashed)" 로 죽는다. 스택트레이스에
파이썬 버전 얘기가 없어서 원인을 찾는 데 시간이 걸린다.

⚠️ PySpark 3.5 가 지원하는 파이썬은 3.8~3.11 이다. 그보다 높으면 워커가 죽는다.
   시스템 기본 파이썬(3.13·3.14)으로 venv 를 만들면 걸린다. README 참고.
"""

from __future__ import annotations

import os
import sys
import warnings

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

# 워커가 죽고 나서 원인을 찾는 것보다 미리 말해주는 게 낫다.
if sys.version_info >= (3, 12):
    warnings.warn(
        f"Python {sys.version_info.major}.{sys.version_info.minor} 에서는 "
        "PySpark 3.5 워커가 죽는다 (지원 범위 3.8~3.11). "
        "venv 를 3.11 로 다시 만들 것 — README 참고.",
        RuntimeWarning,
        stacklevel=1,
    )
