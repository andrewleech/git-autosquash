"""Test that man page documentation stays in sync with CLI implementation."""

import re
import subprocess
from pathlib import Path

from typer.testing import CliRunner


def test_man_page_documents_all_cli_flags():
    """Verify man page OPTIONS section documents all flags from --help output."""
    # Use Typer's CliRunner to capture CLI help output reliably
    from git_autosquash.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    help_text = result.stdout

    # Extract flags from help output
    # Matches patterns like: --flag  or  --flag TEXT  or  -f, --flag
    flag_pattern = r"(?:^|\s+)(-[a-z]|--[a-z][a-z-]+)(?:\s|,|\[|$)"
    cli_flags = set(re.findall(flag_pattern, help_text, re.MULTILINE))

    # Read man page
    man_page_path = Path(__file__).parent.parent / "man" / "git-autosquash.1"
    man_page_content = man_page_path.read_text()

    # Extract flags from man page OPTIONS section
    # Man page uses format: \fB\-\-flag\fR or \fB\-f\fR (with escaped hyphens)
    options_section = re.search(
        r'\.SH "OPTIONS"(.*?)\.SH ', man_page_content, re.DOTALL
    )
    assert options_section, "OPTIONS section not found in man page"

    # Match escaped hyphens in troff: \- becomes -
    man_flag_pattern = r"\\fB(\\-[a-z]|\\-\\-[a-z][a-z\\-]+)\\fR"
    man_flags_raw = re.findall(man_flag_pattern, options_section.group(1))
    # Convert \- to - for comparison
    man_flags = {flag.replace("\\-", "-") for flag in man_flags_raw}

    # Compare flags
    missing_from_man = cli_flags - man_flags
    extra_in_man = man_flags - cli_flags

    # Build error message
    errors = []
    if missing_from_man:
        errors.append(
            f"Flags in --help but missing from man page: {sorted(missing_from_man)}"
        )
    if extra_in_man:
        errors.append(f"Flags in man page but not in --help: {sorted(extra_in_man)}")

    assert not errors, "\n".join(errors)


def test_man_page_exists_and_is_valid():
    """Verify man page file exists and has valid troff syntax."""
    man_page_path = Path(__file__).parent.parent / "man" / "git-autosquash.1"
    assert man_page_path.exists(), "man/git-autosquash.1 does not exist"

    # Test man page can be rendered
    result = subprocess.run(
        ["man", "-l", str(man_page_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"man page rendering failed: {result.stderr}"

    # Validate basic structure
    content = man_page_path.read_text()
    required_sections = ["NAME", "SYNOPSIS", "DESCRIPTION", "OPTIONS", "EXAMPLES"]
    for section in required_sections:
        assert f'.SH "{section}"' in content, (
            f"Required section {section} missing from man page"
        )


def test_man_page_in_wheel():
    """Verify man page will be included in wheel via hatchling config."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    pyproject_content = pyproject_path.read_text()

    # Check hatchling shared-data configuration exists
    assert "[tool.hatch.build.targets.wheel.shared-data]" in pyproject_content, (
        "hatchling shared-data config missing from pyproject.toml"
    )

    # Check man page is configured
    assert '"man/git-autosquash.1"' in pyproject_content, (
        "man page not configured in shared-data"
    )
    assert '"share/man/man1/git-autosquash.1"' in pyproject_content, (
        "man page install path not configured correctly"
    )
