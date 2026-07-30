import {useEffect, useState} from 'react'
import {loadRuntimeConfig, reloadRuntimeConfig} from '../lib/runtimeConfig'
import type {RuntimeConfig} from '../lib/api'

/**
 * 简单 hook：mount 时把 runtime config 取出来。
 * 默认用 module-level 缓存；`fresh: true` 时强制重新请求（知识库页需要最新 chat 开关）。
 */
export function useRuntimeConfig(options?: {fresh?: boolean}): RuntimeConfig | null {
  const [config, setConfig] = useState<RuntimeConfig | null>(null)
  const fresh = Boolean(options?.fresh)
  useEffect(() => {
    let canceled = false
    const loader = fresh ? reloadRuntimeConfig : loadRuntimeConfig
    void loader().then((value) => {
      if (!canceled) setConfig(value)
    })
    return () => {
      canceled = true
    }
  }, [fresh])
  return config
}
