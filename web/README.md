# Planora Web

The web workspace is a browser client for the Python scheduler API. It intentionally keeps
the browser as UI only: solving, timetable CSV import, scoring, conflict checks, local
search improvement, focused CP-SAT polish, and CSV export all run through the same Python
service modules used by the desktop app.

Run the API from the repository root:

```powershell
.venv\Scripts\python.exe -m api.server --host 127.0.0.1 --port 8787
```

Serve the repository with any static server, for example:

```powershell
.venv\Scripts\python.exe -m http.server 8080
```

Open `http://127.0.0.1:8080/web/`.

`src/main.ts` is the typed source. `src/main.js` is checked in so the client works without a Node build toolchain.

When Node is available, the normal TypeScript workflow is:

```powershell
cd web
npm install
npm run typecheck
npm run build
```

The typecheck and build commands use the native TypeScript 7 `tsc` provided by
the `@typescript/native` npm alias. The `typescript` package name resolves to
Microsoft's TypeScript 6 API compatibility package for typescript-eslint, whose
current parser still requires that API. This follows Microsoft's
[side-by-side migration guidance](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/#running-side-by-side-with-typescript-6.0).
`npx tsc --version` reports the build compiler version; `npx tsc6 --version`
reports the lint API compatibility version.

Dependabot updates React/React DOM and their types together, and keeps the
TypeScript/ESLint and Vite/plugin families grouped for major updates as well.

Current API-backed actions:

- load presets and instance JSON
- import timetable CSV
- backend workspace sessions for large instances
- solve, async solve jobs, and portfolio solve
- job polling and Server-Sent Events snapshots
- score / conflict diagnostics
- local-search improve with optional focus term
- focused CP-SAT polish on a penalty neighborhood
- manual move / lock / unlock activity actions
- export the current schedule as CSV
- save and reload local web projects under `data/web_projects`
- view the local API schema at `/openapi.json`
