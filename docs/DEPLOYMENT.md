# GitHub and Render deployment

The Render Blueprint runs the original Python app in one Docker container. FastAPI binds only to loopback port 8000; Streamlit is public on Render's PORT. Startup waits for API health, and either service exiting shuts down the container. APP_PASSWORD protects the Streamlit demo before records or provider operations are accessible. It is a shared demo password, not multiuser account isolation. Only upload synthetic data on this demo.

## GitHub

Authenticate locally with `gh auth login -h github.com -p https -w`. Do not paste tokens in chat. Before pushing, inspect `git status --short` and `git diff --cached --stat` and confirm that `.env`, `.runtime`, virtual environments, uploaded datasets and evaluation outputs are excluded.

If the named remote repository already exists, fetch it into a separate checkout and reconcile its history before adding this implementation. Do not force push over existing commits. If creating a repository, start private unless a public repository is explicitly requested. Connect that repository to Render through the dashboard.

## Render Blueprint

1. Open https://dashboard.render.com and connect GitHub.
2. New → Blueprint → select the repository and its `render.yaml`.
3. Confirm the Free service plan; do not select a paid plan without deciding to incur that cost.
4. Set NVIDIA_API_KEY to your key and APP_PASSWORD to a strong demo password. Store them in Render's environment settings only.
5. Deploy, wait for the build/service health check, then open the returned onrender.com URL.
6. Enter APP_PASSWORD, upload `data/demo_contacts.csv`, review mappings, approve the plan and download the validated CSV.

Set PLANNER_MODE=rules to try the offline baseline without NVIDIA calls. Restart/redeploy after changing provider settings. A failed NVIDIA model request is separate from hosting health.

## Storage and plan limits

The Free Blueprint uses local SQLite only for disposable demo runs. Render Free filesystems are ephemeral: runs disappear after restarts, redeploys or spin-down. Export files before that happens. The free service may cold-start and has limited resources; this deployment caps uploads at 2 MiB. Preserve history later by configuring a durable PostgreSQL DATABASE_URL or a paid persistent disk; neither is automatically provisioned or purchased by this Blueprint.

See https://render.com/docs/free and https://render.com/docs/docker for current platform limitations. Deployment preparation alone does not mean the repository was pushed or the service is live; keep the actual GitHub URL and verified Render URL in the release record once both actions complete.

## Local container check

```bash
docker build -t data-migration-agent .
docker run --rm -p 10000:10000 --env-file .env -e APP_PASSWORD=choose-a-demo-password data-migration-agent
```

Browse http://localhost:10000. Do not include credentials as Docker build arguments or commit them in Dockerfile/render.yaml.
