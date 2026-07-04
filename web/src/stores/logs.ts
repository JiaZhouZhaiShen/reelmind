import { create } from 'zustand';
import type { LogEntry, LogSource, LogResult } from '../api/logs';
import * as logsApi from '../api/logs';
import i18n from '../i18n/config'

const DEFAULT_TAIL = 200;
const POLL_INTERVAL = 5000;

interface LogsState {
  // Sources
  sources: LogSource[];
  sourcesLoading: boolean;
  sourcesError: string | null;

  // Active source
  activeSourceId: string | null;
  activeSourceLabel: string | null;
  activeSourceType: 'docker' | 'file' | null;

  // Log display
  logs: LogEntry[];
  totalLines: number;
  truncated: boolean;
  logsLoading: boolean;
  logsError: string | null;

  // Filters
  levelFilter: string | null;
  searchText: string;
  tailCount: number;

  // Auto-refresh
  autoRefresh: boolean;
  _pollTimer: ReturnType<typeof setInterval> | null;

  // Actions
  fetchSources: () => Promise<void>;
  selectSource: (sourceId: string, label: string, type: 'docker' | 'file') => Promise<void>;
  fetchLogs: () => Promise<void>;
  setLevelFilter: (level: string | null) => void;
  setSearchText: (text: string) => void;
  applySearch: () => Promise<void>;
  setTailCount: (n: number) => void;
  toggleAutoRefresh: () => void;
  startPolling: () => void;
  stopPolling: () => void;
  refresh: () => Promise<void>;
  cleanup: () => void;
}

export const useLogsStore = create<LogsState>((set, get) => ({
  // ── Default state ──
  sources: [],
  sourcesLoading: true,
  sourcesError: null,

  activeSourceId: null,
  activeSourceLabel: null,
  activeSourceType: null,

  logs: [],
  totalLines: 0,
  truncated: false,
  logsLoading: false,
  logsError: null,

  levelFilter: null,
  searchText: '',
  tailCount: DEFAULT_TAIL,

  autoRefresh: false,
  _pollTimer: null,

  // ── Actions ──

  fetchSources: async () => {
    set({ sourcesLoading: true, sourcesError: null });
    try {
      const data = await logsApi.getLogSources();
      set({ sources: data.sources, sourcesLoading: false });
    } catch (e: any) {
      set({
        sourcesError: e?.message || i18n.t('store.logSourceLoadFailed'),
        sourcesLoading: false,
      });
    }
  },

  selectSource: async (sourceId, label, type) => {
    set({
      activeSourceId: sourceId,
      activeSourceLabel: label,
      activeSourceType: type,
      logs: [],
      totalLines: 0,
      truncated: false,
      logsError: null,
      levelFilter: null,
      searchText: '',
    });
    // Fetch logs immediately
    const state = get();
    if (state.autoRefresh) {
      state.stopPolling();
    }
    await get().fetchLogs();
    if (get().autoRefresh) {
      get().startPolling();
    }
  },

  fetchLogs: async () => {
    const { activeSourceId, tailCount, levelFilter, searchText } = get();
    if (!activeSourceId) return;

    set({ logsLoading: true, logsError: null });
    try {
      const data: LogResult = await logsApi.getLogs(activeSourceId, {
        tail: tailCount,
        level: levelFilter || undefined,
        search: searchText || undefined,
      });
      set({
        logs: data.lines || [],
        totalLines: data.total_lines,
        truncated: data.truncated,
        logsLoading: false,
      });
    } catch (e: any) {
      set({
        logsError: e?.message || i18n.t('store.logLoadFailed'),
        logsLoading: false,
      });
    }
  },

  setLevelFilter: (level) => {
    set({ levelFilter: level });
    get().fetchLogs();
  },

  setSearchText: (text) => {
    set({ searchText: text });
  },

  applySearch: async () => {
    await get().fetchLogs();
  },

  setTailCount: (n) => {
    set({ tailCount: n });
    get().fetchLogs();
  },

  toggleAutoRefresh: () => {
    const next = !get().autoRefresh;
    set({ autoRefresh: next });
    if (next) {
      get().startPolling();
    } else {
      get().stopPolling();
    }
  },

  startPolling: () => {
    get().stopPolling();
    const timer = setInterval(() => {
      get().fetchLogs();
    }, POLL_INTERVAL);
    set({ _pollTimer: timer });
  },

  stopPolling: () => {
    const timer = get()._pollTimer;
    if (timer) {
      clearInterval(timer);
      set({ _pollTimer: null });
    }
  },

  refresh: async () => {
    await get().fetchLogs();
  },

  cleanup: () => {
    get().stopPolling();
    set({
      sources: [],
      activeSourceId: null,
      activeSourceLabel: null,
      logs: [],
      logsError: null,
      sourcesError: null,
    });
  },
}));