/** 时间与数字的展示格式化；无效输入一律显示占位符，不抛错。 */

/** ISO 时间 → 本地中文格式；无效输入显示 — */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '—';
  return new Date(ts).toLocaleString('zh-CN', { hour12: false });
}

/** 数字 → 千分位；null/undefined 显示 — */
export function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString('zh-CN');
}

/** 置信度可能是数字或文字等级，统一转展示文本 */
export function fmtConfidence(c: number | string | null | undefined): string {
  if (c === null || c === undefined || c === '') return '—';
  if (typeof c === 'number') return c.toFixed(2);
  return c;
}

/**
 * 未知类型值的展示化（宽松投影字段）：字符串直出、数字/布尔 String、数组/对象 JSON，
 * 超过 maxLen 截断；null/undefined/空串显示"未提供"。
 */
export function fmtUnknown(value: unknown, maxLen = 120): string {
  if (value === null || value === undefined) return '未提供';
  let text: string;
  if (typeof value === 'string') text = value;
  else if (typeof value === 'number' || typeof value === 'boolean') text = String(value);
  else {
    try {
      text = JSON.stringify(value) ?? String(value);
    } catch {
      text = String(value);
    }
  }
  if (!text) return '未提供';
  return text.length <= maxLen ? text : `${text.slice(0, maxLen)}…`;
}
