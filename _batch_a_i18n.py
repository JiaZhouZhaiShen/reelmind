import json

# en.json
with open("D:\\DockerData\\reelmind\\web\\src\\i18n\\locales\\en.json", "r", encoding="utf-8") as f:
    en = json.load(f)
en.update({
    "format.justNow": "Just now",
    "format.secondsAgo": "{{count}}s ago",
    "format.minutesAgo": "{{count}}m ago",
    "format.hoursAgo": "{{count}}h ago",
    "format.monthDay": "{{month}}/{{day}}",
    "format.yearMonth": "{{year}}/{{month}}",
    "store.loadFailed": "Failed to load",
    "store.searchFailed": "Search failed",
    "store.searchRetry": "Search failed, please retry",
    "store.retryFailed": "Retry failed",
    "store.cancelFailed": "Cancel failed",
    "store.cleanupFailed": "Cleanup failed",
    "store.connFailed": "Connection failed, check containers",
    "store.sseDisconnected": "SSE disconnected, status may delay",
    "store.logLoadFailed": "Failed to load logs",
    "store.logSourceLoadFailed": "Failed to load log sources",
    "store.yearLoadFailed": "Failed to load year data",
})
with open("D:\\DockerData\\reelmind\\web\\src\\i18n\\locales\\en.json", "w", encoding="utf-8") as f:
    json.dump(en, f, ensure_ascii=False, indent=2)
    f.write("\n")

# zh.json
with open("D:\\DockerData\\reelmind\\web\\src\\i18n\\locales\\zh.json", "r", encoding="utf-8") as f:
    zh = json.load(f)
zh.update({
    "format.justNow": "刚刚",
    "format.secondsAgo": "{{count}}秒前",
    "format.minutesAgo": "{{count}}分钟前",
    "format.hoursAgo": "{{count}}小时前",
    "format.monthDay": "{{month}}月{{day}}日",
    "format.yearMonth": "{{year}}年{{month}}月",
    "store.loadFailed": "加载失败",
    "store.searchFailed": "搜索失败",
    "store.searchRetry": "搜索失败，请重试",
    "store.retryFailed": "重试失败",
    "store.cancelFailed": "取消失败",
    "store.cleanupFailed": "清理失败",
    "store.connFailed": "连接服务器失败，请检查容器状态",
    "store.sseDisconnected": "SSE 连接断开，实时状态可能延迟",
    "store.logLoadFailed": "无法加载日志",
    "store.logSourceLoadFailed": "无法加载日志源列表",
    "store.yearLoadFailed": "无法加载年份数据",
})
with open("D:\\DockerData\\reelmind\\web\\src\\i18n\\locales\\zh.json", "w", encoding="utf-8") as f:
    json.dump(zh, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("i18n keys added")
