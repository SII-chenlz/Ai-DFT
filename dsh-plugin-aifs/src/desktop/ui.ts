/** Browser half of the AIFS status entry on the DSH Plugins page. */
import { createElement as h, useEffect, useState } from 'react'
import type { RuntimeStatus } from './runtime.ts'

const zh = {
  title: 'AIFS 分子计算助手', description: '规划任务、记录方法依据、生成 REST 输入卡。',
  loading: '正在读取服务状态…', state: '服务状态', version: '版本', data: '数据目录', log: '启动日志',
  retry: '重试启动', error: '错误', address: '本机地址',
  stopped: '已停止', starting: '启动中', ready: '可用', failed: '启动失败', external: '外部服务（调用时检查）',
}
const en: Record<keyof typeof zh, string> = {
  title: 'AIFS molecular assistant', description: 'Plan tasks, preserve method evidence and prepare REST input cards.',
  loading: 'Reading service status…', state: 'Service status', version: 'Version', data: 'Data directory', log: 'Startup log',
  retry: 'Retry startup', error: 'Error', address: 'Local address',
  stopped: 'Stopped', starting: 'Starting', ready: 'Ready', failed: 'Failed', external: 'External service (checked on tool calls)',
}
type Key = keyof typeof zh
type Translate = (key: Key) => string
interface Props { view: string; t: Translate }
interface ClientContext {
  locale: { register(namespace: string, dictionaries: { zh: typeof zh; en: typeof en }): () => void; bind(namespace: string): Translate }
  slots: { inject(name: string, action: () => () => void): () => void; register(metadata: { name: string; id: string; order: number; label: () => string; locale: string; inject: () => object }, component: (props: Props) => unknown): () => void }
  effect(action: () => () => void): void
}
export const inject = ['slots', 'locale']
export function apply(ctx: ClientContext): void {
  const namespace = 'aifs.status'
  const t = ctx.locale.bind(namespace)
  ctx.effect(() => ctx.locale.register(namespace, { zh, en }))
  ctx.effect(() => ctx.slots.inject('plugins.item', () => ctx.slots.register({
    name: 'plugins.item', id: 'aifs', order: 70, label: () => t('title'), locale: namespace, inject: () => ({}),
  }, AifsStatus)))
}
function AifsStatus({ view, t }: Props): unknown {
  const [status, setStatus] = useState<RuntimeStatus | undefined>(undefined)
  const [failure, setFailure] = useState('')
  useEffect(() => {
    if (view === 'summary') return
    const abort = new AbortController()
    const refresh = async () => {
      try {
        const response = await fetch('/api/aifs/status', { signal: abort.signal })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        setStatus(await response.json() as RuntimeStatus)
        setFailure('')
      } catch (error) { if (!abort.signal.aborted) setFailure(String(error)) }
    }
    void refresh()
    const interval = setInterval(() => { void refresh() }, 2000)
    return () => { abort.abort(); clearInterval(interval) }
  }, [view])
  if (view === 'summary') return t('description')
  const rows = status ? [
    [t('state'), t(status.state)], [t('version'), status.version], [t('data'), status.dataDir],
    [t('log'), status.logPath], [t('address'), status.baseUrl || '—'],
    ...status.error ? [[t('error'), status.error]] : [],
  ] : [[t('state'), t('loading')]]
  return h('section', { style: { display: 'grid', gap: 12, overflowWrap: 'anywhere' } },
    ...rows.map(([label, value]) => h('div', { key: label }, h('strong', null, `${label}: `), value)),
    failure ? h('p', { role: 'alert' }, failure) : null,
    h('button', { type: 'button', disabled: status?.state === 'starting', onClick: async () => {
      try {
        const response = await fetch('/api/aifs/retry', { method: 'POST' })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        setStatus(await response.json() as RuntimeStatus)
      } catch (error) { setFailure(String(error)) }
    } }, t('retry')),
  )
}
