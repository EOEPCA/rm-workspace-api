import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'

for (const succeeds of [false, true]) {
  test(`keeps the served UI available during a ${succeeds ? 'successful' : 'failed'} build`, (t) => {
    const root = mkdtempSync(join(tmpdir(), 'workspace-ui-build-'))
    t.after(() => rmSync(root, { recursive: true, force: true }))
    for (const directory of ['bin', 'luigi-shell', 'management/dist', 'management/node_modules', 'dist/management']) {
      mkdirSync(join(root, directory), { recursive: true })
    }
    copyFileSync(new URL('../../build_dist.sh', import.meta.url), join(root, 'build_dist.sh'))
    writeFileSync(join(root, 'dist/ui.html'), 'served-shell')
    writeFileSync(join(root, 'dist/management/index.html'), 'served-frontend')
    writeFileSync(join(root, 'luigi-shell/ui.html'), 'built-shell')
    writeFileSync(join(root, 'management/dist/index.html'), 'local-frontend')
    writeFileSync(join(root, 'management/node_modules/local-package'), 'local-install')
    writeFileSync(join(root, 'management/package.json'), '{}')
    writeFileSync(join(root, 'management/package-lock.json'), '{}')
    writeFileSync(join(root, 'bin/npm'), `#!/bin/sh
test -f '${join(root, 'dist/ui.html')}' || exit 2
test "$PWD" != '${join(root, 'management')}' || exit 3
test -f package.json || exit 4
mkdir -p node_modules dist
echo isolated-install >node_modules/local-package
printf built-frontend >dist/index.html
exit ${succeeds ? 0 : 1}
`, { mode: 0o755 })

    const result = spawnSync('bash', [join(root, 'build_dist.sh')], {
      env: { ...process.env, PATH: `${join(root, 'bin')}:${process.env.PATH}` },
      encoding: 'utf8',
    })

    assert.equal(result.status, succeeds ? 0 : 1, result.stderr)
    assert.equal(readFileSync(join(root, 'dist/ui.html'), 'utf8'), succeeds ? 'built-shell' : 'served-shell')
    assert.equal(readFileSync(join(root, 'dist/management/index.html'), 'utf8'), succeeds ? 'built-frontend' : 'served-frontend')
    assert.equal(readFileSync(join(root, 'management/node_modules/local-package'), 'utf8'), 'local-install')
    assert.equal(readFileSync(join(root, 'management/dist/index.html'), 'utf8'), 'local-frontend')
  })
}
