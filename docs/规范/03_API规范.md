# 03 API 规范

> 对应铁律：R3.1-R3.2
> 作用：前端 API 调用层（web/src/api/）的组织与错误处理边界。

---

## R3.1 API 按域拆分

**边界**：
- `api/` 目录按业务域拆分：base / auth / assets / ai / system / tags / logs
- `client.ts` 只做 barrel 导出，不包含业务代码，≤50 行
- 新 API 必须建新文件，不能在 client.ts 里加方法

```
api/
├── base.ts      # request() + token 管理
├── auth.ts      # 登录/注册
├── assets.ts    # 资产
├── ai.ts        # AI 引擎
├── system.ts    # 系统设置
├── tags.ts      # 标签
├── logs.ts      # 日志
└── client.ts    # barrel 导出（≤50 行）
```

**检查**：
```bash
wc -l web/src/api/client.ts   # ≤50 行（已入 scripts/check.sh R3.1）
```

## R3.2 统一错误展示

**边界**：
- API 调用 catch 到的错误统一写入 store（`setError`）
- 页面顶部用 `GlobalError` 组件展示全局错误
- 每个组件再配合 R2.3 的局部 loading/error 展示

```tsx
// 页面布局
<GlobalError />     ← 页面顶部
<ErrorBoundary>     ← 兜底
  <PageContent />
</ErrorBoundary>
```

**原则**：错误不能吞掉——要么全局提示，要么组件内提示，必须让用户知道发生了什么。
