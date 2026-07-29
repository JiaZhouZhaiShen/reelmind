const LOG_PREFIX = "[ReelMind]";

type LogLevel = "debug" | "info" | "warn" | "error";

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

let minLevel: LogLevel = import.meta.env.DEV ? "debug" : "warn";

const _log = (level: LogLevel, ...args: unknown[]) => {
  if (LOG_LEVELS[level] < LOG_LEVELS[minLevel]) return;
  const fn = (console as any)[level] ?? console.log;
  fn(LOG_PREFIX, `[${level.toUpperCase()}]`, ...args);
};

export const logger = {
  debug: (...args: unknown[]) => _log("debug", ...args),
  info: (...args: unknown[]) => _log("info", ...args),
  warn: (...args: unknown[]) => _log("warn", ...args),
  error: (...args: unknown[]) => _log("error", ...args),

  /** Set minimum level. In production this defaults to "warn". */
  setLevel: (level: LogLevel) => {
    minLevel = level;
  },
};

export default logger;
