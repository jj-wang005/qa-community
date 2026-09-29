import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
const stub = `const auth = globalThis.__testAuth;`
let serial = 0
async function client() {
  globalThis.__testAuth = { state: { accessToken: 'old', refreshToken: 'refresh' }, saveTokens(a,r) { this.state.accessToken=a; this.state.refreshToken=r }, clearAuth() { this.state.accessToken=''; this.state.refreshToken='' } }
  const js = ts.transpileModule(source.replace(/import .*auth.*\r?\n/, stub), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  return import('data:text/javascript;base64,' + Buffer.from(js + `\n// ${serial++}`).toString('base64'))
}
test('concurrent expired requests rotate the refresh token once', async () => {
  const { api } = await client(); let refreshes = 0
  globalThis.fetch = async (path, init) => {
    if (path.endsWith('/refresh')) { refreshes++; await new Promise(r=>setTimeout(r,10)); return Response.json({ access_token:'new', refresh_token:'next' }) }
    return init.headers.get('Authorization') === 'Bearer new' ? Response.json({ ok:true }) : Response.json({}, { status:401 })
  }
  assert.deepEqual(await Promise.all([api('/a'),api('/b')]), [{ok:true},{ok:true}]); assert.equal(refreshes,1)
})
test('invalid login does not refresh or clear another session', async () => {
  const { api } = await client(); let calls=0
  globalThis.fetch = async () => { calls++; return Response.json({ detail:'用户名或密码错误' }, {status:401}) }
  await assert.rejects(api('/api/v1/auth/login'), /用户名或密码错误/); assert.equal(calls,1); assert.equal(globalThis.__testAuth.state.accessToken,'old')
})
test('validation errors are readable and empty success is accepted', async () => {
  const { api } = await client()
  globalThis.fetch = async () => Response.json({detail:[{msg:'标题过长'}]}, {status:422})
  await assert.rejects(api('/a'), /标题过长/)
  globalThis.fetch = async () => new Response(null, {status:204}); assert.equal(await api('/a'),undefined)
})
test('SSE preserves unicode, indentation, CRLF chunk boundaries and final event', async () => {
  const { openEventStream } = await client(); const received=[]
  const bytes = new TextEncoder().encode('data: 中文\r\ndata:   code\r\n\r\nevent: error\r\ndata: failed')
  globalThis.fetch = async () => new Response(new ReadableStream({start(c) { for (const b of bytes) c.enqueue(new Uint8Array([b])); c.close() }}))
  await openEventStream('/ai',{},(event,data)=>received.push([event,data]))
  assert.deepEqual(received,[['message','中文\n  code'],['error','failed']])
})
test('logout during refresh cannot resurrect the session', async () => {
  const { api } = await client()
  globalThis.fetch = async path => {
    if(path.endsWith('/refresh')) { globalThis.__testAuth.clearAuth(); return Response.json({access_token:'new',refresh_token:'next'}) }
    return Response.json({}, {status:401})
  }
  await assert.rejects(api('/a')); assert.equal(globalThis.__testAuth.state.accessToken,'')
})


test('project validation envelope shows field-specific errors', async () => {
  const { api } = await client()
  globalThis.fetch = async () => Response.json({code:422,message:'参数校验失败',errors:[{loc:['body','title'],msg:'标题不能为空'}]}, {status:422})
  await assert.rejects(api('/a'), /标题：标题不能为空/)
})
