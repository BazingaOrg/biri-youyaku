import {lazy, Suspense} from 'react'
import {Redirect, Route, Switch, useSearch} from 'wouter'
import {AppShell} from './components/AppShell'
import {BrowseOmni} from './components/BrowseOmni'
import {ErrorBoundary} from './components/ErrorBoundary'
import {Workspace} from './pages/Workspace'
import {ToastProvider} from './components/ToastProvider'
import {Skeleton} from './components/Skeleton'
import {PageLoading} from './components/Spinner'

const LibraryPage = lazy(() => import('./pages/LibraryPage').then((m) => ({default: m.LibraryPage})))
const SearchPage = lazy(() => import('./pages/SearchPage').then((m) => ({default: m.SearchPage})))
const DocumentPage = lazy(() => import('./pages/DocumentPage').then((m) => ({default: m.DocumentPage})))
const TasksPage = lazy(() => import('./pages/TasksPage').then((m) => ({default: m.TasksPage})))
const TrashPage = lazy(() => import('./pages/TrashPage').then((m) => ({default: m.TrashPage})))
const UpPage = lazy(() => import('./pages/UpPage').then((m) => ({default: m.UpPage})))

function KnowledgeRedirect() {
  const search = useSearch()
  const q = new URLSearchParams(search).get('q')?.trim()
  return <Redirect to={q ? `/search?q=${encodeURIComponent(q)}` : '/search'} />
}

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppShell>
          <BrowseOmni />
          <Switch>
            <Route path="/history">
              <Redirect to="/" />
            </Route>
            <Route path="/knowledge">
              <KnowledgeRedirect />
            </Route>
            <Route path="/search">
              <Suspense fallback={<Skeleton count={5} />}>
                <SearchPage />
              </Suspense>
            </Route>
            <Route path="/doc/:id">
              {(params) => (
                <Suspense fallback={<PageLoading label="加载笔记…" />}>
                  <DocumentPage id={params.id} />
                </Suspense>
              )}
            </Route>
            <Route path="/jobs/:jobId">
              {(params) => <Workspace jobId={params.jobId} />}
            </Route>
            <Route path="/tasks">
              <Suspense fallback={<Skeleton count={6} />}>
                <TasksPage />
              </Suspense>
            </Route>
            <Route path="/trash">
              <Suspense fallback={<Skeleton count={4} />}>
                <TrashPage />
              </Suspense>
            </Route>
            <Route path="/up/:mid">
              {(params) => (
                <Suspense fallback={<Skeleton count={6} />}>
                  <UpPage mid={params.mid} />
                </Suspense>
              )}
            </Route>
            <Route path="/">
              <Suspense fallback={<Skeleton count={6} />}>
                <LibraryPage />
              </Suspense>
            </Route>
          </Switch>
        </AppShell>
      </ToastProvider>
    </ErrorBoundary>
  )
}
