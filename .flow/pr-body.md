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
- honua-release action-pin validation passes for all workflows.
- Native pip resolves/downloads the entire release-tool lock with --require-hashes --only-binary=:all:.
- Downloaded npm archive matches the embedded SHA512; its CLI reports 11.5.1 on native Windows.
- git diff --check passes.

Staged delivery: do not open a PR here. PR CI and post-merge Scorecard/Dependabot re-evaluation remain for the daemon handoff. Trunk presently has 5 code-scanning alerts (one PinnedDependenciesID, four policy/informational) and 3 Dependabot alerts. No alerts dismissed.