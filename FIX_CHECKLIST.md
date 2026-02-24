# Fix Checklist

**Scope**
This checklist covers backend stability, frontend integration, and repo hygiene for `OutfitCompatibility`.

**Decisions**
- [ ] Choose a system of record for auth + user data: Node/Mongo OR Supabase. This determines which APIs and schemas we keep.
- [ ] Decide whether image features (`/recommend`, `/compatibility`) should be real or mocked for demo.

**Backend (Node/Express)**
- [ ] Add npm scripts in `backend/package.json` for `start` and `dev` so the server can be run consistently.
- [ ] Fix password verification: `compare(...)` must be awaited; otherwise any password may pass.
- [ ] Fix JWT verification flow: handle invalid tokens instead of destructuring `null`.
- [ ] Fix schema validation: use `required` instead of `require` in Mongoose schemas.
- [ ] Fix ESM import: `backend/models/clothing.js` should import `./user.js`.
- [ ] Fix CORS: use `origin` (not `host`) and align `CLIENT_HOST` with the frontend dev URL.
- [ ] Implement or remove endpoints referenced by frontend: `/recommend`, `/compatibility`, `/feedback`.
- [ ] Implement `utils/img.js` (multer config) if file upload endpoints stay.
- [ ] Add minimal error handling for missing `DB_LINK`, `JWT_SECRET`, `HTTP_PORT`.

**Frontend (React/Vite)**
- [ ] Replace hardcoded `http://localhost:8001` with `VITE_API_URL` and centralize API base.
- [ ] Align auth flow: either use Node backend or Supabase auth, not both.
- [ ] If using Supabase: mount `AuthProvider` and rewire pages to `useAuth`.
- [ ] If using Node backend: remove Supabase auth context or keep it strictly unused.
- [ ] Wire profile/admin/reports to real data or clearly mark demo-only behavior.

**Security + Repo Hygiene**
- [ ] Remove committed secrets from `backend/.env` and replace with `.env.example`.
- [ ] Ensure `.env` is gitignored.
- [ ] Remove committed `node_modules` from repo and add to `.gitignore`.

**Run Steps (Current, Before Fixes)**
- [ ] Backend: `cd backend` -> `npm install` -> `node app.js`
- [ ] Frontend: `cd frontend/wardo-hub-main` -> `npm install` -> `npm run dev`
