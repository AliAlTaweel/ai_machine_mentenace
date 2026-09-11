type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  data?: unknown;
}

const MAX_BUFFERED_LOGS = 500;
const buffer: LogEntry[] = [];

// Vitest sets import.meta.env.MODE to 'test' — keep the buffer working in
// tests (useful if a test wants to assert on logged events) but skip the
// console noise so test output stays pristine.
const isTestEnv = import.meta.env.MODE === 'test';

function record(level: LogLevel, message: string, data?: unknown): void {
  const entry: LogEntry = { timestamp: new Date().toISOString(), level, message, data };
  buffer.push(entry);
  if (buffer.length > MAX_BUFFERED_LOGS) buffer.shift();

  if (isTestEnv) return;

  const prefix = `[${entry.timestamp}] [app:${level}]`;
  const consoleFn =
    level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
  if (data !== undefined) {
    consoleFn(prefix, message, data);
  } else {
    consoleFn(prefix, message);
  }
}

export const logger = {
  debug: (message: string, data?: unknown) => record('debug', message, data),
  info: (message: string, data?: unknown) => record('info', message, data),
  warn: (message: string, data?: unknown) => record('warn', message, data),
  error: (message: string, data?: unknown) => record('error', message, data),
  getLogs: (): LogEntry[] => [...buffer],
};

declare global {
  interface Window {
    __logs?: () => LogEntry[];
  }
}

if (typeof window !== 'undefined') {
  window.__logs = logger.getLogs;
}
