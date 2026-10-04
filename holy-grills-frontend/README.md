# Holy Grills Frontend

Standalone React and Vite frontend for Holy Grills. The existing backend remains in the sibling `holy-grills-backend` folder and is not included in this frontend deployment.

## Run locally

```bash
npm ci
```

For local development against the hosted Base44 backend, create a local `.env.local` file (do not commit it):

```dotenv
VITE_BASE44_APP_ID=your_base44_app_id
VITE_BASE44_APP_BASE_URL=https://your-app.base44.app
```

Then start the Vite development server:

```bash
npm run dev
```

## Deploy this frontend on Vercel

1. Import the existing `Holy-Grills-` GitHub repository into Vercel.
2. Set the Vercel **Root Directory** to `holy-grills-frontend`.
3. Use the project name/slug `holy-grills-frontend` (lowercase and hyphens, with no spaces).
4. Use the Vite preset, install command `npm ci`, build command `npm run build`, and output directory `dist`.
5. Add these environment variables in Vercel for the environments you deploy:
   - `VITE_BASE44_APP_ID`: the existing Base44 app ID.
   - `VITE_BASE44_APP_BASE_URL`: the hosted Base44 app URL.
   - `VITE_BASE44_FUNCTIONS_VERSION`: only if your Base44 setup requires a specific functions version.
6. Deploy. The included `vercel.json` routes client-side React paths back to the app entry point.

The Vercel project deploys only this frontend folder. The existing `holy-grills-backend` folder is left separate and unchanged.
