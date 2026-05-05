@AGENTS.md

# web/ — Next.js frontend

Next.js 16 + React 19 + Ant Design 6 + TypeScript. Pages router (KHÔNG phải App router).

> **Important**: Next.js 16 has breaking changes. See `AGENTS.md` and check `node_modules/next/dist/docs/` before writing Next.js code — training data may be stale.

## Layout

```
web/src/
├── pages/                    # File-based routes (Pages router)
│   ├── _app.tsx              # Root wrapper, providers
│   ├── _document.tsx
│   ├── index.tsx             # Landing/redirect
│   ├── home.tsx              # Chat interface (main UX)
│   ├── modeling.tsx          # ERD + manifest editor
│   ├── settings.tsx          # Pipeline toggles, model picker
│   ├── setup.tsx             # First-time DB connection wizard
│   └── knowledge/
│       ├── glossary.tsx
│       └── question-sql-pairs.tsx
├── components/
│   ├── VegaChart.tsx         # Vega-Lite renderer
│   ├── layouts/              # HeaderBar, SiderLayout
│   ├── sidebar/              # KnowledgeSidebar
│   ├── debug/                # DebugTracePanel (per-stage trace UI)
│   └── guards/               # RequireConnection
├── contexts/                 # ChatContext, ConnectionContext
├── hooks/
│   └── useApi.ts             # Backend API client (single source)
├── utils/
│   └── types.ts              # Shared TS types
└── styles/
    └── theme.ts              # AntD theme override
```

## Backend contract

`useApi.ts` reads `process.env.NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`). Build-time arg trong `Dockerfile` + `docker-compose.yml`.

Endpoints:
- `/v1/connections/*` — connect/test/status/disconnect
- `/v1/ask`, `/v1/ask/stream` (SSE)
- `/v1/sql/execute`, `/v1/charts/generate`
- `/v1/models`, `/v1/models/{name}`, `/v1/models/auto-describe`
- `/v1/knowledge/glossary`, `/v1/knowledge/sql-pairs`
- `/v1/relationships`, `/v1/settings`, `/v1/deploy`

## Conventions

- **State**: Context API + hooks. Không Redux/Zustand.
- **Styling**: AntD components first; custom CSS chỉ trong `styles/`.
- **Types**: shared types ở `utils/types.ts`. Không inline interface lớn.
- **API calls**: tất cả qua `useApi.ts` — không fetch trực tiếp trong components.

## Dev

```bash
cd web
npm install
npm run dev     # localhost:3000
```

Docker exposes port 3001 (mapped to internal 3000).

## Khi thêm page mới

1. File trong `pages/` (Next.js sẽ auto-route).
2. Reuse `SiderLayout` để giữ navigation nhất quán.
3. Wrap với `RequireConnection` nếu cần DB.
4. Thêm endpoint mới? → đăng ký method trong `useApi.ts`, không gọi `fetch` trực tiếp.
