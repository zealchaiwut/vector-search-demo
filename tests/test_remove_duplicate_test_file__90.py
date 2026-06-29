"""Tests for issue #90: [follow-up] Remove duplicate test file for ticket #74"""
import os
import subprocess


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(REPO_ROOT, "tests")


def test_remove_duplicate_test_file__duplicate_file_deleted():
    """AC: Duplicate test file `test_canvas_optional_deps__74.py` must be deleted."""
    duplicate_file = os.path.join(TESTS_DIR, "test_canvas_optional_deps__74.py")
    assert not os.path.exists(duplicate_file), (
        f"Duplicate file {duplicate_file} still exists. Should be deleted."
    )


def test_remove_duplicate_test_file__comprehensive_file_exists():
    """AC: Comprehensive test file `test_canvas_optional_dep__74.py` must still exist."""
    comprehensive_file = os.path.join(TESTS_DIR, "test_canvas_optional_dep__74.py")
    assert os.path.exists(comprehensive_file), (
        f"Comprehensive file {comprehensive_file} not found. Should be preserved."
    )


def test_remove_duplicate_test_file__comprehensive_tests_pass():
    """AC: Comprehensive test suite for #74 must still pass (no regression)."""
    test_file = os.path.join(TESTS_DIR, "test_canvas_optional_dep__74.py")
    result = subprocess.run(
        ["python3", "-m", "pytest", test_file, "-v", "--tb=short"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Comprehensive test suite failed:\n{result.stdout}\n{result.stderr}"
    )
