"""The quick start in docs/api.md runs as written: the file arrives verified and the message is delivered."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_quick_start_runs():
    text = open(os.path.join(ROOT, "docs", "api.md"), encoding="utf-8").read()
    code = re.search(r"## Quick start.*?```python\n(.*?)```", text, re.S).group(1)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    assert out.returncode == 0, out.stderr
    assert "message note b'hello'" in out.stdout
    assert "final check at the source: ok" in out.stdout
    assert "'verified': 'ok'" in out.stdout
