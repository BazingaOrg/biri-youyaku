import {useMemo, useState} from 'react'
import {AppShell} from './components/AppShell'
import {HistoryPage} from './pages/HistoryPage'
import {HomePage} from './pages/HomePage'
import {JobPage} from './pages/JobPage'
import {ToastProvider} from './components/ToastProvider'

type Page = 'home' | 'history' | 'job'

export default function App() {
  const [page, setPage] = useState<Page>(() => {
    const path = window.location.pathname
    if (path.startsWith('/jobs/')) {
      return 'job'
    }
    if (path === '/history') {
      return 'history'
    }
    return 'home'
  })
  const [jobId, setJobId] = useState<string | null>(() => {
    const match = window.location.pathname.match(/^\/jobs\/([^/]+)/)
    return match?.[1] ?? null
  })
  const navigate = (nextPage: Page, nextJobId?: string) => {
    setPage(nextPage)
    setJobId(nextJobId ?? null)
    const path = nextPage === 'history' ? '/history' : nextPage === 'job' && nextJobId ? `/jobs/${nextJobId}` : '/'
    window.history.pushState({}, '', path)
  }

  const content = useMemo(() => {
    if (page === 'history') {
      return <HistoryPage onOpen={(id) => navigate('job', id)} onHome={() => navigate('home')} />
    }
    if (page === 'job' && jobId) {
      return <JobPage
        jobId={jobId}
        onBack={() => navigate('history')}
      />
    }
    return <HomePage
      onCreated={(id) => navigate('job', id)}
      onHistory={() => navigate('history')}
    />
  }, [page, jobId])

  return (
    <ToastProvider>
      <AppShell>
        {content}
      </AppShell>
    </ToastProvider>
  )
}
