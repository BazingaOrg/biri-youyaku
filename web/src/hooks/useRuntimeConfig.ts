import {useEffect, useState} from 'react'
import {loadRuntimeConfig} from '../lib/runtimeConfig'
import type {RuntimeConfig} from '../lib/api'

/**
 * 简单 hook：mount 时把缓存里的 runtime config 取出来。
 * 第一次会触发 fetch；后续 mount 直接命中 module-level promise，零额外请求。
 */
export function useRuntimeConfig(): RuntimeConfig | null {
  const [config, setConfig] = useState<RuntimeConfig | null>(null)
  useEffect(() => {
    let canceled = false
    void loadRuntimeConfig().then((value) => {
      if (!canceled) setConfig(value)
    })
    return () => {
      canceled = true
    }
  }, [])
  return config
}
