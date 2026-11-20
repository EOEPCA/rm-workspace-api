import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'

test('keeps the served UI when the Docker build fails', (t) => {
  const root = mkdtempSync(join(tmpdir(), 'workspace-ui-build-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  mkdirSync(join(root, 'bin'))
  mkdirSync(join(root, 'dist/management'), { recursive: true })
  copyFileSync(new URL('../../build_dist.sh', import.meta.url), join(root, 'build_dist.sh'))
  writeFileSync(join(root, 'dist/ui.html'), 'served-shell')
  writeFileSync(join(root, 'dist/management/index.html'), 'served-frontend')
  writeFileSync(join(root, 'bin/docker'), `#!/bin/sh
test -f '${join(root, 'dist/ui.html')}' || exit 2
output_dir=
for argument do
  case "$argument" in
    type=local,dest=*) output_dir="\${argument#type=local,dest=}" ;;
  esac
done
test -n "$output_dir" || exit 3
mkdir -p "$output_dir/management"
printf built-shell >"$output_dir/ui.html"
printf built-frontend >"$output_dir/management/index.html"
exit 1
`, { mode: 0o755 })

  const result = spawnSync('bash', [join(root, 'build_dist.sh')], {
    env: { ...process.env, PATH: `${join(root, 'bin')}:${process.env.PATH}` },
    encoding: 'utf8',
  })

  assert.equal(result.status, 1, result.stderr)
  assert.equal(readFileSync(join(root, 'dist/ui.html'), 'utf8'), 'served-shell')
  assert.equal(readFileSync(join(root, 'dist/management/index.html'), 'utf8'), 'served-frontend')
})
