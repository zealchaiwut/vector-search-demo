"""
Acceptance tests for issue #56: Add DATABASE_URL to .env.example for postgres backend

AC1 - .env.example contains a DATABASE_URL entry with a valid example value
      (e.g. DATABASE_URL=postgresql://vectoruser:vectorpass@localhost:5432/vectordb)
AC2 - The DATABASE_URL entry appears in the same section as or adjacent to
      the existing POSTGRES_HOST/PORT/DB/USER/PASSWORD entries
AC3 - The README Backends section references DATABASE_URL alongside POSTGRES_* variables
AC4 - An operator copying .env.example verbatim and setting DB_BACKEND=postgres
      can start the application without hitting the "DATABASE_URL is required" error
      (i.e. DATABASE_URL must be an uncommented, active assignment)
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_EXAMPLE_PATH = os.path.join(REPO_ROOT, ".env.example")
README_PATH = os.path.join(REPO_ROOT, "README.md")


def read_env_example():
    with open(ENV_EXAMPLE_PATH) as f:
        return f.read()


def read_readme():
    with open(README_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1: .env.example contains DATABASE_URL with a valid postgres connection string
# ---------------------------------------------------------------------------


def test_add_database_url__env_example_has_uncommented_database_url():
    # AC1: DATABASE_URL must appear as an active (uncommented) assignment
    content = read_env_example()
    matches = re.findall(r'^DATABASE_URL=(.+)$', content, re.MULTILINE)
    assert matches, (
        "DATABASE_URL= (uncommented) not found in .env.example. "
        "Add 'DATABASE_URL=postgresql://vectoruser:vectorpass@localhost:5432/vectordb'."
    )


def test_add_database_url__database_url_value_is_postgresql_dsn():
    # AC1: the example value must be a postgresql:// connection string
    content = read_env_example()
    matches = re.findall(r'^DATABASE_URL=(.+)$', content, re.MULTILINE)
    assert matches, "DATABASE_URL= (uncommented) not found in .env.example"
    url = matches[0].strip()
    assert url.startswith("postgresql://"), (
        f"DATABASE_URL example value must start with 'postgresql://', got: {url!r}"
    )


def test_add_database_url__database_url_includes_credentials():
    # AC1: the example value should include user:password so it is a complete connection string
    content = read_env_example()
    matches = re.findall(r'^DATABASE_URL=(.+)$', content, re.MULTILINE)
    assert matches, "DATABASE_URL= (uncommented) not found in .env.example"
    url = matches[0].strip()
    assert "@" in url, (
        f"DATABASE_URL example must include credentials (user:pass@host), got: {url!r}. "
        "Expected format: postgresql://vectoruser:vectorpass@localhost:5432/vectordb"
    )


# ---------------------------------------------------------------------------
# AC2: DATABASE_URL appears adjacent to POSTGRES_* entries
# ---------------------------------------------------------------------------


def test_add_database_url__database_url_near_postgres_vars():
    # AC2: DATABASE_URL must appear in the same section as POSTGRES_HOST/PORT/DB/USER/PASSWORD
    content = read_env_example()
    lines = content.splitlines()

    db_url_lines = [i for i, line in enumerate(lines) if re.match(r'^DATABASE_URL=', line)]
    postgres_lines = [i for i, line in enumerate(lines) if re.match(r'^POSTGRES_', line)]

    assert db_url_lines, "No uncommented DATABASE_URL= line found in .env.example"
    assert postgres_lines, "No POSTGRES_* lines found in .env.example"

    db_url_idx = db_url_lines[0]
    nearest_pg = min(postgres_lines, key=lambda i: abs(i - db_url_idx))
    distance = abs(db_url_idx - nearest_pg)

    assert distance <= 10, (
        f"DATABASE_URL (line {db_url_idx + 1}) is {distance} lines away from nearest "
        f"POSTGRES_* var (line {nearest_pg + 1}). They must be in the same section."
    )


# ---------------------------------------------------------------------------
# AC3: README Backends section references DATABASE_URL alongside POSTGRES_* vars
# ---------------------------------------------------------------------------


def test_add_database_url__readme_backends_section_exists():
    # AC3 prerequisite: README must have a Backends section
    content = read_readme()
    assert re.search(r'^## Backends\b', content, re.MULTILINE), (
        "README does not contain a '## Backends' section"
    )


def test_add_database_url__readme_backends_mentions_database_url():
    # AC3: README Backends section must reference DATABASE_URL
    content = read_readme()
    backends_match = re.search(r'^## Backends\b', content, re.MULTILINE)
    assert backends_match, "README '## Backends' section not found"

    after_backends = content[backends_match.start():]
    next_section = re.search(r'\n## ', after_backends[4:])
    if next_section:
        backends_section = after_backends[:next_section.start() + 4]
    else:
        backends_section = after_backends

    assert "DATABASE_URL" in backends_section, (
        "README Backends section does not mention DATABASE_URL. "
        "Add a reference to DATABASE_URL alongside the postgres backend description."
    )


def test_add_database_url__readme_backends_mentions_postgres_vars():
    # AC3: README Backends section must also reference POSTGRES_* variables near DATABASE_URL
    content = read_readme()
    backends_match = re.search(r'^## Backends\b', content, re.MULTILINE)
    assert backends_match, "README '## Backends' section not found"

    after_backends = content[backends_match.start():]
    next_section = re.search(r'\n## ', after_backends[4:])
    if next_section:
        backends_section = after_backends[:next_section.start() + 4]
    else:
        backends_section = after_backends

    has_postgres_var = any(var in backends_section for var in (
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"
    ))
    assert has_postgres_var, (
        "README Backends section does not reference any POSTGRES_* variables. "
        "Document DATABASE_URL alongside POSTGRES_HOST/PORT/DB/USER/PASSWORD."
    )


# ---------------------------------------------------------------------------
# AC4: Verbatim copy of .env.example provides a working DATABASE_URL
# ---------------------------------------------------------------------------


def test_add_database_url__env_example_database_url_is_not_only_a_comment():
    # AC4: DATABASE_URL must not be commented-out only; a verbatim copy must set the var
    content = read_env_example()
    lines = content.splitlines()

    uncommented = [line for line in lines if re.match(r'^DATABASE_URL=', line)]
    assert uncommented, (
        "DATABASE_URL is absent or only present as a comment (#) in .env.example. "
        "An operator who copies .env.example verbatim must get a DATABASE_URL value "
        "so they don't hit 'DATABASE_URL is required for DB_BACKEND=postgres'."
    )
