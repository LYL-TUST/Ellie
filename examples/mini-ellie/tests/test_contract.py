import subprocess
import sys
from pathlib import Path

import mini_ellie


def test_mini_ellie_module_and_public_exports():
    assert mini_ellie.Ellie is not None
    assert mini_ellie.FakeModelClient is not None
    assert not hasattr(mini_ellie, "MiniAgent")
    result = subprocess.run([sys.executable, "-m", "mini_ellie", "--help"], capture_output=True, text=True, check=True)
    assert "Teaching-sized Ellie agent harness" in result.stdout


def test_readme_main_mapping_points_to_existing_files():
    repo_root = Path(__file__).resolve().parents[3]
    main_files = [
        "Ellie/cli.py",
        "Ellie/runtime.py",
        "Ellie/agent_loop.py",
        "Ellie/context_manager.py",
        "Ellie/providers/clients.py",
        "Ellie/tool_executor.py",
        "Ellie/tools.py",
        "Ellie/task_state.py",
        "Ellie/run_store.py",
        "Ellie/workspace.py",
    ]
    for path in main_files:
        assert (repo_root / path).exists()

