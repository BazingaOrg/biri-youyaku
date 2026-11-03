import {createContext, useContext} from 'react'
import type {Job} from '../lib/api'

export interface TaskAlertsContextValue {
  running: Job[]
  failed: Job[]
  badge: number
  refresh: () => Promise<void>
}

export const TaskAlertsContext = createContext<TaskAlertsContextValue | null>(null)

export function useTaskAlerts() {
  const context = useContext(TaskAlertsContext)
  if (!context) {
    throw new Error('useTaskAlerts must be used inside TaskAlertsProvider')
  }
  return context
}
