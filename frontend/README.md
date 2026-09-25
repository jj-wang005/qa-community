# QA Community Frontend

QA Community 的 Vue 3 + TypeScript 前端，与 FastAPI 后端一起存放在同一个仓库中。

## 功能

- 注册、登录、Access Token 刷新与退出。
- 问题热门/最新列表、问题详情、发布问题和回答。
- 回答点赞与采纳。
- AI 多轮会话、POST SSE 解析和会话 ID 保留。
- Agent `approval_required` 事件的批准/拒绝交互。
- 桌面端与移动端响应式布局。

## 本地启动

先启动 FastAPI 后端：

```powershell
cd ..
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

再启动前端：

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会将 `/api` 代理到 `http://127.0.0.1:8000`。后端同时默认允许 `localhost:5173` 和 `127.0.0.1:5173` 的跨域请求，其他部署地址通过后端 `.env` 中的 `CORS_ORIGINS` 配置。

## 验证

```powershell
npm run build
```

构建命令会先执行 Vue/TypeScript 类型检查，然后输出到 `dist/`。
