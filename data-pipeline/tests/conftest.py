"""Spark 가 워커로 띄울 파이썬을 현재 인터프리터로 고정한다.

이걸 안 하면 Windows 에서 executor 가 시스템 PATH 의 python 을 찾다가
"Python worker exited unexpectedly (crashed)" 로 죽는다. 스택트레이스에
파이썬 버전 얘기가 없어서 원인을 찾는 데 시간이 걸린다.

⚠️ PySpark 3.5 는 Python 3.13 을 지원하지 않는다. 3.11 로 venv 를 만들 것.
   README 참고.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
