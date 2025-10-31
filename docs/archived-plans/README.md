# Archived Implementation Plans

This directory contains implementation plans that were superseded by better approaches or completed features.

## man-page-implementation-plan.md

**Status:** Superseded by pipx integration

**Original approach:** Manual man page installation with documentation for users

**Superseded by:** pipx automatic man page installation via hatchling shared-data

**Date archived:** 2025-10-31

The original plan recommended manual installation instructions and relying on downstream packagers. However, research revealed that pipx (v1.4.0+, December 2023) supports automatic man page installation when packages include man pages in `share/man/man<N>/` in the wheel.

The implemented approach uses hatchling's `shared-data` feature:
```toml
[tool.hatch.build.targets.wheel.shared-data]
"man/git-autosquash.1" = "share/man/man1/git-autosquash.1"
```

This provides automatic installation for pipx/uv users while still allowing manual installation for pip users or downstream packagers.
