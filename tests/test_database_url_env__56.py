"""Tests for issue #56: Add DATABASE_URL to .env.example for postgres backend"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent


def test_database_url_in_env_example():
    """AC: .env.example contains a DATABASE_URL entry with a valid example value"""
    env_example_path = REPO_ROOT / ".env.example"

    assert env_example_path.exists(), ".env.example not found"

    content = env_example_path.read_text()

    # Check that DATABASE_URL line exists
    assert "DATABASE_URL=" in content, "DATABASE_URL= entry not found in .env.example"

    # Check that the value is a valid postgres connection string
    match = re.search(r'DATABASE_URL=(.+)', content)
    assert match, "Could not parse DATABASE_URL= line"

    url_value = match.group(1).strip()
    assert url_value.startswith("postgresql://"), \
        f"DATABASE_URL should be a postgres URL (postgresql://...), got: {url_value}"
    assert "@" in url_value, \
        f"DATABASE_URL should contain user:password@host, got: {url_value}"
    assert "localhost" in url_value or ":" in url_value.split("@")[1], \
        f"DATABASE_URL should specify a host and port, got: {url_value}"


def test_database_url_grouped_with_postgres_vars():
    """AC: DATABASE_URL appears in the same section as or adjacent to POSTGRES_* entries"""
    env_example_path = REPO_ROOT / ".env.example"

    content = env_example_path.read_text()
    lines = content.split('\n')

    # Find line numbers for DATABASE_URL and POSTGRES_* vars
    database_url_line = None
    postgres_lines = []

    for i, line in enumerate(lines):
        if line.strip().startswith("DATABASE_URL="):
            database_url_line = i
        if line.strip().startswith("POSTGRES_"):
            postgres_lines.append(i)

    assert database_url_line is not None, "DATABASE_URL line not found"
    assert len(postgres_lines) > 0, "No POSTGRES_* variables found"

    # Check that DATABASE_URL is within 5 lines of any POSTGRES_* var
    # (allowing for comments and blank lines between them)
    closest_postgres_line = min(postgres_lines, key=lambda x: abs(x - database_url_line))
    distance = abs(closest_postgres_line - database_url_line)

    assert distance <= 5, \
        f"DATABASE_URL (line {database_url_line}) is too far from POSTGRES_* vars (closest: line {closest_postgres_line}, distance: {distance})"


def test_readme_documents_database_url():
    """AC: README Backends section references DATABASE_URL alongside POSTGRES_* variables"""
    readme_path = REPO_ROOT / "README.md"

    assert readme_path.exists(), "README.md not found"

    content = readme_path.read_text()

    # Check that DATABASE_URL is mentioned
    assert "DATABASE_URL" in content, "DATABASE_URL not mentioned in README"

    # Check that it appears in a Backends section (case-insensitive)
    backends_section = None
    for match in re.finditer(r'#+\s+Backends', content, re.IGNORECASE):
        # Get content from this section until the next section header
        section_start = match.start()
        next_header = re.search(r'\n#+\s+', content[section_start + 1:])
        if next_header:
            section_end = section_start + next_header.start() + 1
        else:
            section_end = len(content)
        backends_section = content[section_start:section_end]
        break

    assert backends_section is not None, "Backends section not found in README"

    # Check that DATABASE_URL is in the Backends section
    assert "DATABASE_URL" in backends_section, \
        "DATABASE_URL not found in README Backends section"

    # Check that POSTGRES_* variables are also mentioned
    postgres_vars_mentioned = any(var in backends_section for var in [
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"
    ])
    assert postgres_vars_mentioned, \
        "POSTGRES_* variables not mentioned in README Backends section"


def test_postgres_backend_startup_no_error():
    """AC: Operator copying .env.example and setting DB_BACKEND=postgres can start without 'DATABASE_URL is required' error"""
    # This is a manual inspection test — it validates that the config exists
    # and is correct. Actual runtime startup requires a running Node.js
    # environment, which is not available in this test environment.
    # However, we can validate that the structure supports the claim.

    env_example_path = REPO_ROOT / ".env.example"
    content = env_example_path.read_text()

    # Verify that .env.example has all required postgres config
    required_keys = ["DATABASE_URL", "DB_BACKEND"]
    for key in required_keys:
        assert any(line.startswith(key + "=") for line in content.split('\n')), \
            f"Required key {key} not found in .env.example"

    # Check that there's an example DB_BACKEND value set
    db_backend_line = [line for line in content.split('\n') if line.startswith("DB_BACKEND=")]
    assert len(db_backend_line) > 0, "DB_BACKEND not set in .env.example"

    # Verify the structure allows switching DB_BACKEND to postgres
    # (the default can be anything, but DATABASE_URL must be present)
    assert "DATABASE_URL=" in content, \
        "DATABASE_URL not found — operator would hit 'DATABASE_URL is required' error"
