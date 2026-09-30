import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

# 테스트는 공개 예시값으로 돈다 (실제 rules.local.yaml 을 쓰지 않는다)
os.environ["HARNESS_RULES_LOCAL"] = str(ROOT / "rules.local.example.yaml")


def gate(name: str, run: Path, *extra: str):
    """판정 스크립트를 실제로 실행한다 → (exit code, stdout)."""
    script = ROOT / "scripts" / ("approve.py" if name == "approve" else f"judge/{name}.py")
    p = subprocess.run([sys.executable, str(script), str(run), *extra],
                       capture_output=True, text=True, env=os.environ.copy())
    return p.returncode, p.stdout + p.stderr


@pytest.fixture
def run(tmp_path):
    from factory import build_run
    return build_run(tmp_path)


@pytest.fixture
def g():
    return gate
