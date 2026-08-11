// fuzzy.ts — 档案字段模糊匹配 (2026-08-11 老板规则)
// 客户/品牌/类别等下拉或自动补全字段统一支持:
//   ① 原文包含 (中文名片段、编号片段)
//   ② 拼音首字母 (如 "ynx" 命中 "印尼大雄"... 实际按每个字首字母)
//   ③ 全拼 (如 "yindaxiong")
//   ④ 数字/大写字母片段 (编号中的数字段、字母段, 大小写不敏感)
import { pinyin } from 'pinyin-pro'

// 缓存: 同一个文本的拼音变体只算一次 (596 个客户 × 每次敲键)
const cache = new Map<string, { lower: string; initials: string; full: string }>()

function variants(text: string) {
  let v = cache.get(text)
  if (!v) {
    v = {
      lower: text.toLowerCase(),
      // 首字母: 印尼大雄 → yndx
      initials: pinyin(text, { pattern: 'first', toneType: 'none', type: 'string' }).replace(/\s/g, '').toLowerCase(),
      // 全拼: 印尼大雄 → yindaxiong
      full: pinyin(text, { toneType: 'none', type: 'string' }).replace(/\s/g, '').toLowerCase(),
    }
    cache.set(text, v)
  }
  return v
}

/** 核心: input 是否模糊命中 text */
export function fuzzyMatch(input: string, text: string): boolean {
  const q = input.trim().toLowerCase().replace(/\s/g, '')
  if (!q) return true
  const v = variants(text)
  return v.lower.replace(/\s/g, '').includes(q) || v.initials.includes(q) || v.full.includes(q)
}

/** AntD Select 的 filterOption (label 为字符串, 如 "Q025 - 印尼大雄") */
export function selectFilter(input: string, option?: { label?: unknown; value?: unknown }): boolean {
  const label = String(option?.label ?? option?.value ?? '')
  return fuzzyMatch(input, label)
}

/** AntD AutoComplete 的 filterOption (option.value 为字符串) */
export function autoCompleteFilter(input: string, option?: { value?: unknown }): boolean {
  return fuzzyMatch(input, String(option?.value ?? ''))
}
