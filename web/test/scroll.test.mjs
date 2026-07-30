import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('WeekNavigator uses the shared reduced-motion scroll behavior', async () => {
  const [scroll, navigator] = await Promise.all([
    readFile(new URL('../src/lib/scroll.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/WeekNavigator.tsx', import.meta.url), 'utf8'),
  ])

  assert.match(scroll, /matchMedia\('\(prefers-reduced-motion: reduce\)'\)\.matches \? 'auto' : 'smooth'/)
  assert.match(navigator, /import \{preferredScrollBehavior\} from '\.\.\/lib\/scroll'/)
  assert.match(navigator, /behavior: preferredScrollBehavior\(\)/)
  assert.doesNotMatch(navigator, /behavior: 'smooth'/)
})
