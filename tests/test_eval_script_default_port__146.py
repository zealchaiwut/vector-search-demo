"""Tests for issue #146: align eval script default port to 8000 (not 7070)"""
import os
import re


def test_run_eval_default_port():
    """AC: run_eval.py defaults to http://localhost:8000/search"""
    eval_script = os.path.join(
        os.path.dirname(__file__), "..", "src", "eval", "run_eval.py"
    )
    with open(eval_script, encoding="utf-8") as f:
        content = f.read()

    # Check the SEARCH_URL default (line 46)
    assert 'http://localhost:8000/search' in content, \
        "run_eval.py must default to port 8000, not 7070"

    # Ensure 7070 is NOT the default
    assert 'localhost:7070' not in content, \
        "run_eval.py should not use port 7070"


def test_run_ablation_default_port():
    """AC: run_ablation.py defaults to http://localhost:8000/search"""
    ablation_script = os.path.join(
        os.path.dirname(__file__), "..", "src", "eval", "run_ablation.py"
    )
    with open(ablation_script, encoding="utf-8") as f:
        content = f.read()

    # Check _DEFAULT_SEARCH_URL
    assert 'http://localhost:8000/search' in content, \
        "run_ablation.py must default to port 8000, not 7070"

    # Ensure 7070 is NOT the default
    assert 'localhost:7070' not in content, \
        "run_ablation.py should not use port 7070"


def test_readme_documents_port_8000():
    """AC: README.md documents the default port as 8000"""
    readme = os.path.join(
        os.path.dirname(__file__), "..", "src", "eval", "README.md"
    )
    with open(readme, encoding="utf-8") as f:
        content = f.read()

    # Check that the running section mentions port 8000
    assert 'default port 8000' in content or '8000' in content, \
        "README.md should document default port 8000"

    # Check example shows port 8000
    assert 'python3 src/eval/run_eval.py' in content, \
        "README.md should show how to run the script"
