"""
GitHub Actions 用：根據當前日期輸出執行模式到 GITHUB_OUTPUT。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from run import determine_mode
import os

mode = determine_mode()
github_output = os.environ.get("GITHUB_OUTPUT", "")
if github_output:
    with open(github_output, "a") as f:
        f.write(f"mode={mode}\n")
        f.write("force=false\n")
print(f"mode={mode}")
