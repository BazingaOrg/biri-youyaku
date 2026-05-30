export interface FriendlyError {
  title: string
  message: string
  actionLabel?: string
}

const STAGE_LABELS: Record<string, string> = {
  FETCHING_META: '识别视频',
  DOWNLOADING_AUDIO: '下载音频',
  TRANSCRIBING: '语音转写',
  SUMMARIZING: '生成总结',
  EMAILING: '发送邮件',
}

function describeStage(stage?: string): string | null {
  if (!stage) return null
  return STAGE_LABELS[stage] || null
}

export function friendlyError(code?: string, message?: string, stage?: string): FriendlyError {
  if (code === 'STAGE_TIMEOUT') {
    const stageLabel = describeStage(stage)
    return {
      title: stageLabel ? `${stageLabel} 超时` : '这一步超时了',
      message: stageLabel
        ? `「${stageLabel}」超过了安全等待时间，任务并没有卡死。可以稍后重试，或换一段更短的视频。`
        : '任务没有卡死，但当前阶段超过了安全等待时间。可以稍后重试，或换一个更短的视频。',
      actionLabel: '重试',
    }
  }
  if (message?.includes('LLM_API_KEY')) {
    return {
      title: '还没有配置大模型 Key',
      message: '请在后端 .env 配置 LLM_API_KEY。',
    }
  }
  if (message?.includes('B 站元信息') || message?.includes('地区限制')) {
    return {
      title: '拿不到视频信息',
      message: '可能是地区限制、视频需要登录，或 B 站 Cookie 失效。检查后端 BILI_SESSDATA 后重试。',
      actionLabel: '重试',
    }
  }
  if (message?.includes('No video formats found') || message?.includes('yt-dlp')) {
    return {
      title: '下载音频失败',
      message: '多半是 Cookie 失效或视频权限受限。更新 B 站 Cookie 后重试。',
      actionLabel: '重试',
    }
  }
  if (message?.includes('HTTP 4') || message?.includes('HTTP 5')) {
    return {
      title: '大模型接口异常',
      message: '模型服务返回了错误。可以换模型，或稍后重试。',
      actionLabel: '重试',
    }
  }
  return {
    title: '任务失败',
    message: message || '任务遇到未知错误，可以重试或查看服务端日志。',
    actionLabel: '重试',
  }
}
