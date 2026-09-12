# Generated Python and TypeScript Client Publication

The repository publishes generated clients from the same immutable `v<Version>`
tag as the schema, conformance fixtures, BSR coordinate, and .NET package:

| Registry | Coordinate | Workflow |
| --- | --- | --- |
| PyPI | `geospatial-grpc==<Version>` | `publish-python-client.yml` |
| npm | `@honua/geospatial-grpc@<Version>` | `publish-typescript-client.yml` |

Generated files remain build outputs and are never committed. Each workflow
generates from the tagged `.proto` files, builds once, installs the exact local
artifact as a smoke test, and uploads it as an immutable Actions artifact. The
Python workflow records a `SHA256SUMS` file alongside the wheel and sdist as
part of that artifact; it is a run record only and is never passed to the
publish step, which sees just the wheel and sdist.
A `workflow_dispatch` run with no `tag` input stops there and cannot publish.
An exact `v<Version>` tag pushed to the repository is the primary publication
trigger; its version must match the .NET package, both client manifests,
`conformance/VERSION`, the protocol major, and `CHANGELOG.md`.

Both workflows also accept a `tag` input on `workflow_dispatch` to re-run
publication for an already-created, already-built `v<Version>` tag (for
example, recovering from a failed or misconfigured publish on the original
tag-push run) without creating a new tag. They check out that tag, re-validate
the release contract against it, and publish exactly as the tag-push trigger
would.

## First-publish operator checklist

Before creating the stable tag:

- Configure the `production` environment to admit only protected `v*` tags.
- PyPI and npm both use **Trusted Publishing — no long-lived `PYPI_API_TOKEN`
  or `NPM_TOKEN` secret exists or may be created.**
  - On pypi.org, configure (or when rotating ownership, re-create) a Trusted
    Publisher for the `geospatial-grpc` project: publisher GitHub, repository
    `honua-io/geospatial-grpc`, workflow `publish-python-client.yml`,
    environment `production`. The publish job exchanges its OIDC identity for
    a short-lived upload token via `pypa/gh-action-pypi-publish`.
  - On npmjs.com, configure a Trusted Publisher for `@honua/geospatial-grpc`:
    publisher GitHub Actions, repository `honua-io/geospatial-grpc`, workflow
    `publish-typescript-client.yml`, environment `production`. `npm publish`
    exchanges the same OIDC identity for a short-lived token and attaches
    provenance.
  - In both cases the trusted publisher's repository, workflow filename, and
    environment must match the workflow exactly or the exchange is rejected.
- Confirm the package coordinates are unoccupied. The workflows repeat this
  check before publishing: an unoccupied coordinate publishes, an occupied
  coordinate is compared byte-for-byte (PyPI file digest, npm `dist.integrity`)
  against the freshly built artifact — identical skips the publish step with a
  green job, and any difference fails closed with both digests logged. They
  never overwrite a published version.
- Run both workflows with `workflow_dispatch` (no `tag` input) from the intended
  release commit. Inspect the generated wheel/sdist and npm tarball artifacts
  and smoke results.
- Confirm all repository CI checks are green on the release commit.

Then create and push the single protected `v<Version>` tag. Do not create a
language-specific tag. The Python, TypeScript, and stable protocol workflows
all consume that tag independently. If any validation or credential preflight
fails, do not publish another language manually; correct the configuration and
rerun the failed job using its already-built artifact.

After publication, both workflows download the public package anonymously,
compare its SHA-256 digest with the build artifact, and import the client from a
clean environment. Record the workflow run URLs, package coordinates, tag, Git
commit, and artifact hashes on the release tracker. Publication is not complete
until these public-consumption jobs pass.

These workflows deliberately do not create credentials, tags, releases, or
registry namespaces. They only publish on an operator-created protected tag.
