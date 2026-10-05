const { readdirSync } = require('node:fs')
const { join } = require('node:path')
const { spawnSync } = require('node:child_process')
for (const file of readdirSync(__dirname)
  .filter((name) => name.endsWith('.cjs') && name !== 'run.cjs')
  .sort()) {
  console.log(`Browser check: ${file}`)
  const result = spawnSync(process.execPath, [join(__dirname, file)], {
    stdio: 'inherit',
    env: process.env,
  })
  if (result.status !== 0) {
    process.exitCode = result.status || 1
    break
  }
}
