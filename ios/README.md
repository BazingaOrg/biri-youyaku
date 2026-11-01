# 笔哩 iOS

自用、只读的 SwiftUI 客户端，复用项目现有 FastAPI 服务。首版不创建任务、不上传文件，也不取消、重试、重新生成或删除内容。

## 运行

- Xcode 16 或更新版本；当前工程使用 Xcode 27 文件系统同步组。
- iOS 17 或更新版本。
- 打开 `Biri.xcodeproj`，选择 `Biri` scheme 与模拟器运行。
- 首次启动填写 FastAPI 根地址，例如 `http://192.168.1.10:8000`，不要附加 `/v1`。
- 服务器启用 `API_TOKEN` 时，在 App 中填写同一个 Token。

命令行验证（本机 Xcode 未设为默认开发者目录时）：

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  xcodebuild -project ios/Biri.xcodeproj -scheme Biri \
  -destination 'platform=iOS Simulator,name=iPhone 17' build

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  xcodebuild -project ios/Biri.xcodeproj -scheme Biri \
  -destination 'platform=iOS Simulator,name=iPhone 17' test
```

真机运行需要在 Xcode 的 Signing & Capabilities 中选择自己的开发团队。

当前工程没有 XCUITest target，以下 UI 路径需手动回归：

- 在笔记页输入关键词时不应自动搜索，也不应提前显示“无结果”；点击输入法 Return 后才显示加载状态或搜索结果。修改尚未提交的关键词后，分页仍使用上次提交的关键词和范围；搜索进行中切换范围时，旧响应不得覆盖新范围；取消搜索后恢复资料库。
- 笔记页只显示合并数量后的导航标题，不再显示重复的吸顶“全部笔记”标题；阅读页正文标题不与动态导航标题重复。
- 打开含多级标题的笔记，从目录选择靠后的章节；关闭目录后正文应滚动到对应标题。
- 已连接且未修改服务器信息时不显示主操作按钮；修改地址或输入新 Token 后显示“保存并重新连接”。已保存 Token 只显示固定掩码，移除操作位于凭据分组。
- 失败、已完成和进行中分类没有任务时不显示“加载更多”；有历史分页时才显示统一的品牌色加载行。
- 在浅深色模式和大字体下检查任务状态胶囊、长标题、设置页及加载更多行，确保没有挤压或半截分隔线。

## 架构

- `Core/Models.swift`：API DTO、领域状态与阅读目的地；使用 snake_case 解码。
- `Core/APIClient.swift`：唯一的 HTTP 边界；负责 Bearer 鉴权、查询参数、错误映射和游标类型。
- `Core/AppModel.swift`：服务器连接与应用级配置；连接成功后才保存配置。
- `Core/KeychainStore.swift`：Token 使用 `ThisDeviceOnly` Keychain 项，不同步到 iCloud。
- `Features/*`：每个功能由 SwiftUI View 和 `@MainActor` ViewModel 组成。ViewModel 不直接创建网络请求，而是通过 `BiriServicing` 接收服务，便于替换和单元测试。
- `Core/Markdown.swift`：保留原文的轻量分块解析；标题、段落、列表、引用和代码块使用原生 Text 渲染。

网络模型只依赖 Foundation；界面状态留在 MainActor。功能之间通过值类型模型和 `NavigationStack` 目的地连接，不共享一个大型全局状态对象。

## UI / UX

- 三个一级入口：笔记、任务、设置；每栏有独立导航栈。
- 资料库使用系统 `searchable` 与 `searchScopes`，不额外制造搜索 Tab。
- 阅读页使用分段控件切换笔记/字幕，目录用底部 Sheet，复制、字号和原页面收进更多菜单。
- 正文字号同时作用于笔记和字幕，并叠加系统 Dynamic Type。
- 加载、空数据、错误、分页失败、部分字幕搜索不可用均有明确状态；支持下拉刷新。
- 进行中的任务每 5–8 秒轮询，回到前台时刷新。iOS 挂起后不会承诺实时更新，也没有后台推送。
- 任务接口没有可靠的总进度百分比，因此只展示真实阶段，不展示虚构进度。

## 网络与安全

- 局域网允许 HTTP，只开启 `NSAllowsLocalNetworking`，没有开启任意 HTTP 加载。
- 公网服务应使用有效 HTTPS 和访问控制。原生 App 没有浏览器 CORS 限制，但仍受网络可达性和 ATS 约束。
- 自用远程访问优先考虑 Tailscale / WireGuard。Cloudflare Access 等额外鉴权层需要单独适配，当前未实现。
- Token 不写入源码、UserDefaults、日志或导航状态。
- 首版不提供完整离线资料库；URLSession 使用系统协议缓存，离线内容可用性不作保证。

## 已知边界

- Markdown 支持常用块级结构和行内样式；复杂表格按原始文本保留，不宣称完整 CommonMark 渲染。
- 旧资料只有 `job_id` 时通过任务详情读取总结；若任务已关联正式文档，则优先读取正式文档。
- 搜索和列表使用服务端游标分页。已完成/失败筛选共用服务端终态游标，再在客户端细分。
- 时间戳通过原页面 `t` 参数打开，不在 App 内播放视频。
