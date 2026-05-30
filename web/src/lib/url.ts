// 旧路径保留为薄重导出：新代码应直接 import 'lib/biliUrl'。
// 留这个文件是为了避免一次性改动所有调用方。
export {
  extractBiliUrl,
  normalizeBiliUrl,
  isValidBiliUrl,
  sanitizeBiliInput,
} from './biliUrl'
