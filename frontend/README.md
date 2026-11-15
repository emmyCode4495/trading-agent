# Aether Web Frontend

React + TypeScript + Vite + Tailwind trading terminal for the multi-exchange live bot.

## Quick start

```bash
# From this directory
npm install
npm run dev
```

The Vite dev server runs on http://localhost:5173 and proxies `/api/*` to the FastAPI backend at http://localhost:8000.

Start the backend first:

```bash
# From project root
cd ..
# (activate your venv if needed)
uvicorn app.api:app --reload --port 8000
```

## Structure

- `src/api` — typed client for the FastAPI backend
- `src/pages` — Dashboard, Markets, Positions, Bot, Settings
- `src/components` — shared UI
- `src/types` — shared API types (ready to extract to a package for Expo later)

## Hybrid plan

This web app is the full terminal. The Expo mobile companion will reuse the same API contract and (later) shared types.
