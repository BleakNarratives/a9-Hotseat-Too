# Changelog

All notable changes to Hotseat-Too are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-11-24

### Added

- Packaged Python distribution with the `hotseat` console entry point.
- Bundled desktop war room and `/m` companion assets under `hotseat_core/web`.
- Installed-wheel CI smoke test for `/`, `/m`, `/mobile.css`, and `/mobile.js`.
- MIT license and release documentation.

### Changed

- Unified the runtime, bridge health endpoint, frontend contract, and package
  metadata on version `0.5.0`.
- Provider status labels now say `CONFIGURED` rather than `READY`, matching the
  bridge's credential-presence semantics.
- Static assets resolve through package resources, so `hotseat --serve` works
  from a wheel as well as a source checkout.

### Security

- Redact `?token=` values from `--verbose` request logs.
- Send `Referrer-Policy: no-referrer` with UI assets.

## Earlier work

- Provider fallback, per-role model routing, credential-safe provider status,
  structured market anchors, the arena console, and the phone/tablet companion
  shell were delivered before the 0.5.0 packaging release.
