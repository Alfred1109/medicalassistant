import { format, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';

export type AppDatePattern = 'minute' | 'day' | 'dayZh' | 'minuteZh' | 'locale' | 'localeShort';

const DATE_FNS_PATTERNS: Partial<Record<AppDatePattern, string>> = {
  dayZh: 'yyyy年MM月dd日',
  minuteZh: 'yyyy年MM月dd日 HH:mm',
};

function pad(value: number): string {
  return value.toString().padStart(2, '0');
}

function clockText(date: Date, pattern: 'minute' | 'day'): string {
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  if (pattern === 'day') return day;
  return `${day} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 页面展示用的日期格式。空值与非法值的回退由调用方给出，格式规则只留这一处。 */
export function formatAppDate(
  value: Date | string | null | undefined,
  pattern: AppDatePattern,
  options?: { empty?: string; invalid?: string },
): string {
  const empty = options?.empty ?? '';
  const invalid = options?.invalid ?? empty;
  if (value == null || value === '') return empty;
  try {
    const date = value instanceof Date
      ? value
      : (pattern === 'dayZh' || pattern === 'minuteZh' ? parseISO(value) : new Date(value));
    if (Number.isNaN(date.getTime())) return invalid;
    if (pattern === 'minute' || pattern === 'day') return clockText(date, pattern);
    if (pattern === 'locale') return date.toLocaleString();
    if (pattern === 'localeShort') {
      return date.toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
      });
    }
    return format(date, DATE_FNS_PATTERNS[pattern] as string, { locale: zhCN });
  } catch {
    return invalid;
  }
}
