"""
CI Test Suite: Repository Documentation, Privacy & Access Guard Integrity
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_required_documentation_files_exist():
    """Verify all public documentation files referenced in README.md exist and are non-empty."""
    expected_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "warehouse_comparison.md",
        REPO_ROOT / "docs" / "authenticity_and_governance.md",
        REPO_ROOT / "docs" / "free_tier_guide.md",
        REPO_ROOT / "docs" / "benchmarking_strategy.md",
    ]
    for doc in expected_docs:
        assert doc.is_file(), f"Missing documentation file: {doc}"
        assert doc.stat().st_size > 100, f"Documentation file appears empty: {doc}"


def test_private_notes_are_gitignored():
    """Ensure RESEARCH.md and CI_TEST_PLAN.md are listed in .gitignore."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "RESEARCH.md" in gitignore
    assert "CI_TEST_PLAN.md" in gitignore


def test_access_guard_configured():
    """Ensure local git hooks and GitHub Actions access-guard workflow enforce owner identity."""
    allowed_email = "with.u.venu@gmail.com"
    allowed_user = "venu-madhav-data-engineer"

    pre_commit = (REPO_ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8")
    pre_push = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "access-guard.yml").read_text(encoding="utf-8")

    for content in (pre_commit, pre_push, workflow):
        assert allowed_email in content
        assert allowed_user in content
