import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

// Bind the locally built (or byte-verified public) tarball into the committed
// third-party dependency lock before npm ci exercises the real installation.
const [destination, tarball, version] = process.argv.slice(2);
if (!destination || !tarball || !version) {
  throw new Error('Usage: prepare-typescript-smoke.mjs <destination> <tarball> <version>');
}
const lock = JSON.parse(await readFile(new URL('../requirements/typescript-smoke.lock.json', import.meta.url), 'utf8'));
const archive = path.resolve(tarball);
const archiveBytes = await readFile(archive);
const spec = `file:${archive.replaceAll('\\', '/')}`;
lock.packages[''].dependencies['@honua/geospatial-grpc'] = spec;
lock.packages['node_modules/@honua/geospatial-grpc'] = {
  version,
  resolved: spec,
  integrity: `sha512-${createHash('sha512').update(archiveBytes).digest('base64')}`,
  dependencies: { '@bufbuild/protobuf': '2.14.0' },
};
await mkdir(destination, { recursive: true });
await writeFile(path.join(destination, 'package.json'), JSON.stringify({
  ...lock.packages[''], private: true,
}, null, 2) + '\n');
await writeFile(path.join(destination, 'package-lock.json'), JSON.stringify(lock, null, 2) + '\n');
