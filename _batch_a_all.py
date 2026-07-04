import re

def add_i18n_import(content):
    lines = content.split("\n")
    last_import = -1
    for i, l in enumerate(lines):
        if l.startswith("import "):
            last_import = i
    if last_import >= 0:
        lines.insert(last_import + 1, "import i18n from '\''../i18n/config'\''")
    return "\n".join(lines)

# === stores/asset.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\asset.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u5df2\u5904\u7406\u8d44\u4ea7: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u8d44\u4ea7\u5217\u8868: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u5f52\u6863\u8d44\u4ea7: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u8d44\u4ea7\u8be6\u60c5: '", "i18n.t('store.loadFailed') + ': '")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\asset.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("asset.ts done")

# === stores/ai.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\ai.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
# Replace Chinese error messages (some are Unicode-escapd in source)
c = c.replace("'\u83b7\u53d6\u6a21\u5757\u914d\u7f6e\u5931\u8d25: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'\u4fdd\u5b58\u6a21\u5757\u914d\u7f6e\u5931\u8d25: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'\u83b7\u53d6\u6a21\u578b/GPU \u72b6\u6001\u5931\u8d25: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'SSE \u8fde\u63a5\u65ad\u5f00\uff0c\u5b9e\u65f6\u72b6\u6001\u53ef\u80fd\u5ef6\u8fdf'", "i18n.t('store.sseDisconnected')")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\ai.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("ai.ts done")

# === stores/admin.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\admin.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u7ba1\u7406\u5458\u9762\u677f: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace('"\u8fde\u63a5\u670d\u52a1\u5668\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u5bb9\u5668\u72b6\u6001"', "i18n.t('store.connFailed')")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\admin.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("admin.ts done")

# === stores/adminJobs.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\adminJobs.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u52a0\u8f7d\u4efb\u52a1\u5931\u8d25'", "i18n.t('store.loadFailed')")
c = c.replace("'\u91cd\u8bd5\u5931\u8d25'", "i18n.t('store.retryFailed')")
c = c.replace("'\u53d6\u6d88\u5931\u8d25'", "i18n.t('store.cancelFailed')")
c = c.replace("'\u6e05\u7406\u5931\u8d25'", "i18n.t('store.cleanupFailed')")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\adminJobs.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("adminJobs.ts done")

# === stores/library.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\library.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u5e93\u5217\u8868: '", "i18n.t('store.loadFailed') + ': '")
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u7edf\u8ba1\u6570\u636e: '", "i18n.t('store.loadFailed') + ': '")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\library.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("library.ts done")

# === stores/logs.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\logs.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u65e5\u5fd7\u6e90\u5217\u8868'", "i18n.t('store.logSourceLoadFailed')")
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u65e5\u5fd7'", "i18n.t('store.logLoadFailed')")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\logs.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("logs.ts done")

# === stores/search.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\search.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u641c\u7d22\u5931\u8d25: '", "i18n.t('store.searchFailed') + ': '")
c = c.replace("'\u641c\u7d22\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5'", "i18n.t('store.searchRetry')")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\search.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("search.ts done")

# === stores/grid.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\grid.ts", "r", encoding="utf-8") as f:
    c = f.read()
c = add_i18n_import(c)
c = c.replace("'\u65e0\u6cd5\u52a0\u8f7d\u5e74\u4efd\u6570\u636e'", "i18n.t('store.yearLoadFailed')")
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\grid.ts", "w", encoding="utf-8") as f:
    f.write(c)
print("grid.ts done")

print("\nAll stores done!")
