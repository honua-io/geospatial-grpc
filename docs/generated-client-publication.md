# Generated Python and TypeScript Client Publication

The repository publishes generated clients from the same immutable `v<Version>`
tag as the schema, conformance fixtures, BSR coordinate, and .NET package:

| Registry | Coordinate | Workflow |
| --- | --- | --- |
| PyPI | `geospatial-grpc==<Version>` | `publish-python-client.yml` |
| npm | `@honua/geospatial-grpc@<Version>` | `publish-typescript-client.yml` |

Generated files remain build outputs and are never committed. Each workflow
generates from the tagged `.proto` files, builds once, installs the exact local
artifact as a smoke test, and uploads it as an immutable Actions artifact.
Manual dispatch stops there and cannot publish. An exact `v<Version>` tag is the
only publication trigger; its version must match the .NET package, both client
manifests, `conformance/VERSION`, the protocol major, and `CHANGELOG.md`.

## First-publish operator checklist

Before creating the stable tag:

- Configure the `production` environment to admit only protected `v*` tags.
- Add the organization/environment Actions secret `PYPI_API_TOKEN`, scoped to
  create and upload the `geospatial-grpc` PyPI project.
- Add the organization/environment Actions secret `NPM_TOKEN`, scoped to
  publish the public `@honua/geospatial-grpc` npm package in the `@honua` org.
- Confirm the package coordinates are unoccupied. The workflows repeat this
  check and fail closed rather than overwriting or skipping an existing release.
- Run both workflows with `workflow_dispatch` from the intended release commit.
  Inspect the generated wheel/sdist and npm tarball artifacts and smoke results.
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
