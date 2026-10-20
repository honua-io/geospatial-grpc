ci: verify publication tooling by digest and patch urllib3

## Summary

The Trusted Publishing follow-up to #105 introduced an unhashed npm CLI install, and the Python publication lock now has three urllib3 advisories. Verify the npm 11.5.1 archive by its SHA512 before extracting or executing it, then publish using that exact CLI. Upgrade urllib3 to 2.8.0 with PyPI wheel/sdist SHA256 values.

Refs #105; code-scanning alert #125 and Dependabot alerts #5, #6, #7.

## Changes Made

- Replace the global npm install with a digest-checked archive and direct CLI execution.
- Update the Python release-tool lock to urllib3 2.8.0.
- Correct action version comments for checkout and PyPI publishing without changing their SHAs.

## Breaking Changes

None.

## Testing

- Native Windows actionlint 1.7.12 passes for all workflows.
- honua-release `tools/check_action_pins.py` (trunk 4642e4d, with the reusable-workflow reachability check enabled) passes for all workflows.
- Native pip resolves/downloads the entire release-tool lock with --require-hashes --only-binary=:all:.
- Downloaded npm archive matches the embedded SHA512; its CLI reports 11.5.1 on native Windows.
- git diff --check passes.
- Re-verified after merging trunk e6be082 (#147): actionlint, honua-release action-pin validation, Linux-target hash-locked download of the release-tool lock, and the npm 11.5.1 SHA512 against the registry `dist.integrity`.

Trunk e6be082 (2026-10-20) has 5 code-scanning alerts (one PinnedDependenciesID, four policy/informational) and 3 Dependabot alerts. Scorecard and Dependabot re-evaluate on trunk after merge. No alerts dismissed.