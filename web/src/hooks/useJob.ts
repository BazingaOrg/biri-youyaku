import {useCallback, useEffect, useState} from 'react'
import {getJob, type Job} from '../lib/api'

export function useJob(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!jobId) {
      return
    }
    try {
      const response = await getJob(jobId)
      setJob(response.job)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载任务失败')
    }
  }, [jobId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return {job, setJob, error, refresh}
}
