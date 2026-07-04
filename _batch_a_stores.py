import re

# === stores/asset.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\stores\\asset.ts", "r", encoding="utf-8") as f:
    content = f.read()

# Add i18n import
lines = content.split("\n")
last_import = max(i for i, l in enumerate(lines) if l.startswith("import "))
lines.insert(last_import + 1, "import i18n from '../i18n/config'")
content = "\n".join(lines)

# Replace Chinese strings
content = content.replace("'\u65e0\u6cd5\u52a0\u8f7d\u5df2\u5904\u7406\u8d44\u4ea7: '", "i18n.t('store.loadFailed') + ': '")
content = content.replace("'\u65e0\u6cd5\u52a0\u8f7d\u8d44\u4ea7\u5217\u8868: '", "i18n.t('store.loadFailed') + ': '")
content = content.replace("'\u65e0\u6cd5\u52a0\u8f7d\u5f52\u6863\u8d44\u4ea7: '", "i18n.t('store.loadFailed') + ': '")
content = content.replace("'\u65e0\u6cd5\u52a0\u8f7d\u8d44\u4ea7\u8be6\u60c5: '", "i18n.t('store.loadFailed') + ': '")

with open("D:\\DockerData\\reelmind\\web\\src\\stores\\asset.ts", "w", encoding="utf-8") as f:
    f.write(content)
print("asset.ts done")
