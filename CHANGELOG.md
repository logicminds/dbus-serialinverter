# Changelog

All notable changes to this project will be documented in this file.

Starting with tagged releases (`v*`), release notes are generated automatically from commits since the previous tag and published in GitHub Releases.

## Unreleased

### Fix

- Eliminated `WARNING: USING OUTDATED REGISTRATION METHOD!` on startup by passing `register=False`
  to `VeDbusService` and calling `register()` explicitly after all mandatory D-Bus paths are added.

### Feature set: Reliability and runtime hardening

- Strengthened startup/config validation and runtime safeguards, including MAX_AC_POWER validation,
  safer poll execution, refresh/publish gating, and explicit fatal-signal propagation.
- Improved Modbus handling with connection reuse, response-size checks, register address bounds,
  safer power-limit behavior, and clearer decoding/formatting paths.

### Feature set: Test coverage and verification expansion

- Added and expanded comprehensive tests across inverter base behavior, dbushelper lifecycle,
  Solis/Samlex paths, GLib integration, and regression coverage.
- Coverage tooling and policy were reinforced to keep quality gates strict and stable.

### Feature set: Samlex support and Modbus architecture

- Introduced Samlex EVO 4024 support and follow-up improvements for batching and robustness.
- Refactored shared inverter communication logic by extracting a reusable Modbus base.


### Feature set: CI, developer workflow, and docs

- Added CI + lint automation and improved local development ergonomics with conda/GLib guidance.
- Added/updated contributor-facing docs and repository process files.


### Feature set: Release automation (local changes pending release)

- Added a tag-triggered GitHub Actions release workflow for `v*` tags.
- Added release artifacts containing only `conf/` and `etc/` with SHA256 checksums.
- Added automatic release-note generation from git history since the previous tag.
- Added a generated `CHANGELOG-<tag>.md` file to each GitHub Release.

## v0.1.0 (Mar 24, 2023)

### Included commits

- initial commit
- add dummy inverter for testing
- some code cleanup
