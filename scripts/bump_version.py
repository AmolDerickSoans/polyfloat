#!/usr/bin/env python3
"""Version bump script with automatic changelog updates."""
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def get_version_from_pyproject():
    """Extract current version from pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()
    match = re.search(r'^version = "(\d+)\.(\d+)\.(\d+)"', content, re.MULTILINE)
    if match:
        return tuple(map(int, match.groups()))
    raise ValueError("Could not find version in pyproject.toml")


def write_version_to_pyproject(version):
    """Update version in pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()
    new_content = re.sub(
        r'^version = "\d+\.\d+\.\d+"',
        f'version = "{version}"',
        content,
        flags=re.MULTILINE,
    )
    pyproject.write_text(new_content)


def update_changelog(version):
    """Add new version entry to CHANGELOG.md."""
    changelog = PROJECT_ROOT / "CHANGELOG.md"
    today = date.today().isoformat()

    if not changelog.exists():
        changelog.write_text(
            f"# Changelog\n\n## [{version}] - {today}\n\n### Changed\n- Version bump\n"
        )
        return

    content = changelog.read_text()
    new_entry = f"## [{version}] - {today}\n\n### Changed\n- Version bump\n\n"
    changelog.write_text(new_entry + content)


def update_init_version(version):
    """Update __version__ in __init__.py."""
    init_file = PROJECT_ROOT / "src" / "polycli" / "__init__.py"
    content = init_file.read_text()
    new_content = re.sub(
        r'^__version__ = "\d+\.\d+\.\d+"',
        f'__version__ = "{version}"',
        content,
        flags=re.MULTILINE,
    )
    init_file.write_text(new_content)


def bump_version(part):
    """Bump version in pyproject.toml and update CHANGELOG."""
    major, minor, patch = get_version_from_pyproject()

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        print(f"Unknown version part: {part}")
        sys.exit(1)

    new_version = f"{major}.{minor}.{patch}"
    write_version_to_pyproject(new_version)
    update_init_version(new_version)
    update_changelog(new_version)
    print(f"Bumped version to {new_version}")
    print("\nNext steps:")
    print("  1. Review changes: git diff")
    print("  2. Commit: git add -A && git commit -m 'Bump to v{version}'")
    print("  3. Tag: git tag v{version}")
    print("  4. Push: git push origin main --tags")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: bump_version.py <major|minor|patch>")
        sys.exit(1)
    bump_version(sys.argv[1])
