import {useEffect, useState} from 'react'
import {loadRuntimeConfig} from '../lib/runtimeConfig'
import type {RuntimeConfig} from '../lib/api'

/** 简单 hook：mount 时把 runtime config 取出来（module-level 缓存）。 */
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
