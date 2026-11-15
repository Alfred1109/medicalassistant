import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';

export type AppDatePattern = 'minute' | 'day' | 'dayZh' | 'minuteZh' | 'locale' | 'localeShort'
  | 'localeZh' | 'localeZh24' | 'localeDay' | 'localeTime' | 'dayEn' | 'zoned' | 'relative' | 'notification';

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
  pattern: string,
  options?: { empty?: string; invalid?: string; assumeUtc?: boolean; parse?: 'native' | 'iso'; timeZone?: string; now?: Date },
): string {
  const empty = options?.empty ?? '';
  const invalid = options?.invalid ?? empty;
  if (value == null || value === '') return empty;
  try {
    const source = typeof value === 'string' && options?.assumeUtc && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
      ? `${value}Z` : value;
    const nativePattern = ['minute', 'day', 'locale', 'localeShort', 'localeZh', 'localeZh24', 'localeDay', 'localeTime', 'dayEn', 'zoned', 'relative', 'notification'].includes(pattern);
    const date = source instanceof Date ? source
      : (options?.parse === 'iso' || (!options?.parse && !nativePattern) ? parseISO(source) : new Date(source));
    if (Number.isNaN(date.getTime())) return invalid;
    if (pattern === 'minute' || pattern === 'day') return clockText(date, pattern);
    if (pattern === 'locale') return date.toLocaleString();
    if (pattern === 'localeZh') return date.toLocaleString('zh-CN');
    if (pattern === 'localeZh24') return date.toLocaleString('zh-CN', { hour12: false });
    if (pattern === 'localeDay') return date.toLocaleDateString();
    if (pattern === 'localeTime') return date.toLocaleTimeString();
    if (pattern === 'dayEn') return new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric' }).format(date);
    if (pattern === 'relative') return formatDistanceToNow(date, { addSuffix: true, locale: zhCN });
    if (pattern === 'notification') {
      const days = Math.floor(((options?.now ?? new Date()).getTime() - date.getTime()) / 86400000);
      if (days === 0 || days === 1) return `${days === 0 ? '今天' : '昨天'} ${format(date, 'HH:mm')}`;
      return days < 7 ? `${days}天前` : clockText(date, 'day');
    }
    if (pattern === 'zoned') {
      return new Intl.DateTimeFormat('zh-CN', {
        timeZone: options?.timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZoneName: 'longOffset',
      }).format(date).replace(/GMT/g, 'UTC');
    }
    if (pattern === 'localeShort') {
      return date.toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
      });
    }
    return format(date, DATE_FNS_PATTERNS[pattern as AppDatePattern] ?? pattern, { locale: zhCN });
  } catch {
    return invalid;
  }
}
