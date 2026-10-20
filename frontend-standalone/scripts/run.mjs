// The launcher uses only Node built-ins, so `npm run dev` also works before npm ci.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(root);
const command = process.argv[2] ?? 'dev';
const extra = process.argv.slice(3);
const npmCli = process.env.npm_execpath ?? join(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js');
const run = (args) => {
  const result = spawnSync(process.execPath, args, { cwd: root, stdio: 'inherit', env: process.env });
  if (result.error) { console.error(result.error.message); process.exit(1); }
  if (result.status !== 0) process.exit(result.status ?? 1);
};

const [major, minor] = process.versions.node.split('.').map(Number);
if (major < 22 || (major === 22 && minor < 12)) {
  console.log('Using a temporary Node 22 runtime for this frontend (your installed Node stays unchanged).');
  run([npmCli, 'exec', '--yes', '--package=node@22.23.3', '--', 'node', fileURLToPath(import.meta.url), command, ...extra]);
  process.exit(0);
}

const marker = join(root, 'node_modules/.standalone-runtime');
const fingerprint = createHash('sha256').update(readFileSync('package-lock.json')).update(`${major}/${process.platform}/${process.arch}`).digest('hex');
if (!existsSync('node_modules/vite/bin/vite.js') || !existsSync(marker) || readFileSync(marker, 'utf8') !== fingerprint) {
  console.log('Installing the standalone frontend dependencies...');
  run([npmCli, 'ci', '--no-audit', '--no-fund']);
  writeFileSync(marker, fingerprint);
}

if (command === 'build') {
  run(['node_modules/typescript/bin/tsc', '-b']);
  run(['node_modules/vite/bin/vite.js', 'build', ...extra]);
} else if (command === 'test') {
  run(['node_modules/@playwright/test/cli.js', 'test', ...extra]);
} else if (command === 'dev' || command === 'preview') {
  run(['node_modules/vite/bin/vite.js', ...(command === 'preview' ? ['preview'] : []), ...extra]);
} else {
  console.error(`Unknown command: ${command}`);
  process.exit(1);
}
