import test from 'node:test'
import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import * as api from '../src/api/index.js'
import client, { onUnauthorized } from '../src/api/client.js'
import { resourceApi } from '../src/api/resources.js'
import { taskApi } from '../src/api/tasks.js'

const src = fileURLToPath(new URL('../src/', import.meta.url))
async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  return (
    await Promise.all(
      entries.map((entry) => {
        const filename = path.join(directory, entry.name)
        return entry.isDirectory() ? sourceFiles(filename) : filename
      })
    )
  )
    .flat()
    .filter((filename) => /\.(js|vue)$/.test(filename))
}

test('shared stays independent of business modules and HTTP client construction is centralized', async () => {
  const clients = []
  for (const filename of await sourceFiles(src)) {
    const source = await readFile(filename, 'utf8')
    if (/axios\s*\.\s*create\s*\(/.test(source)) clients.push(path.relative(src, filename))
    if (!filename.startsWith(path.join(src, 'shared') + path.sep)) continue
    for (const match of source.matchAll(/\b(?:from\s*|import\s*\(?\s*)['"]([^'"]+)['"]/g)) {
      const imported = match[1]
      const target = imported.startsWith('.')
        ? path.resolve(path.dirname(filename), imported)
        : imported.startsWith('@/')
          ? path.resolve(src, imported.slice(2))
          : null
      if (target)
        assert.ok(
          target.startsWith(path.join(src, 'shared') + path.sep),
          `${filename} imports ${imported}`
        )
    }
  }
  assert.deepEqual(clients, ['api/client.js'])
})

test('API barrel preserves object identity and domain requests share envelope handling', async () => {
  assert.equal(api.resourceApi, resourceApi)
  assert.equal(api.taskApi, taskApi)
  assert.equal(api.onUnauthorized, onUnauthorized)
  assert.deepEqual(
    Object.keys(api).sort(),
    [
      'actorApi',
      'authApi',
      'downloadApi',
      'externalSearchApi',
      'genreApi',
      'onUnauthorized',
      'personalCredentialApi',
      'recommendationApi',
      'resourceApi',
      'settingsApi',
      'sourceApi',
      'taskApi',
      'viewingApi',
    ].sort()
  )
  const original = client.defaults.adapter
  const requests = []
  client.defaults.adapter = async (config) => {
    requests.push(config.url)
    return {
      status: 200,
      data: { code: 0, message: 'ok', data: { marker: config.url } },
      headers: {},
      config,
    }
  }
  try {
    assert.deepEqual((await resourceApi.getList()).data, { marker: '/resources' })
    assert.deepEqual((await taskApi.listJobs()).data, { marker: '/tasks/jobs' })
    assert.deepEqual(requests, ['/resources', '/tasks/jobs'])
  } finally {
    client.defaults.adapter = original
  }
})
