// 从总结 markdown 提炼 TOC 目录与思维导图数据。纯字符串处理，不依赖渲染库。

export interface Heading {
  level: number // 2 = ##, 3 = ###
  text: string
}

export interface MindmapNode {
  topic: string
  id: string
  children?: MindmapNode[]
}

export interface MindmapData {
  nodeData: MindmapNode
}

/** 去掉行内 markdown 标记，留纯文本。 */
function stripInline(s: string): string {
  return s
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // 图片
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1') // 链接 → 文本
    .replace(/[*_`~>#]/g, '') // 强调 / 代码 / 引用 / 多余 #
    .replace(/\s+/g, ' ')
    .trim()
}

function truncate(s: string, max: number): string {
  const t = s.trim()
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

/** 按文档顺序取 ## / ### 标题，忽略围栏代码块里的 #。 */
export function parseHeadings(markdown: string): Heading[] {
  const out: Heading[] = []
  let inFence = false
  for (const raw of (markdown ?? '').split('\n')) {
    const line = raw.trim()
    if (/^(```|~~~)/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const m = /^(#{2,3})\s+(.*)$/.exec(line)
    if (m) {
      const text = stripInline(m[2])
      if (text) out.push({level: m[1].length, text})
    }
  }
  return out
}

/**
 * 把总结 markdown 转成 mind-elixir 的 nodeData 树：
 * 标题作为根 → `##` 主干 → `###` 分支；子弹 / 段落作为叶子（截断）。
 * 直接吃已存的 markdown，所以历史总结也能出脑图，不需要额外 LLM 调用。
 */
export function summaryToMindmap(markdown: string, rootTopic: string): MindmapData {
  let counter = 0
  const nextId = () => `n${counter++}`
  const root: MindmapNode = {topic: truncate(rootTopic || '总结', 40), id: 'root', children: []}

  let h2: MindmapNode | null = null
  let h3: MindmapNode | null = null
  let inFence = false

  const add = (parent: MindmapNode, text: string): MindmapNode | null => {
    const topic = stripInline(text)
    if (!topic) return null
    const node: MindmapNode = {topic: truncate(topic, 60), id: nextId()}
    ;(parent.children ??= []).push(node)
    return node
  }

  for (const raw of (markdown ?? '').split('\n')) {
    const line = raw.trim()
    if (/^(```|~~~)/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence || !line) continue

    let m: RegExpExecArray | null
    if ((m = /^##\s+(.*)$/.exec(line))) {
      h2 = add(root, m[1])
      h3 = null
    } else if ((m = /^###\s+(.*)$/.exec(line))) {
      h3 = add(h2 ?? root, m[1])
    } else if ((m = /^[-*+]\s+(.*)$/.exec(line)) || (m = /^\d+\.\s+(.*)$/.exec(line))) {
      add(h3 ?? h2 ?? root, m[1])
    } else {
      add(h3 ?? h2 ?? root, line)
    }
  }

  if (!root.children?.length) {
    root.children = [{topic: truncate(stripInline(markdown) || '（空）', 60), id: nextId()}]
  }
  return {nodeData: root}
}
