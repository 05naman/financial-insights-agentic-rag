# Deploy the backend to Google Cloud Run

The image bundles the embedding models and a read-only copy of the search index. Users and chats live in Postgres (Neon),
because Cloud Run's disk is wiped on restart.

1. **Neon:** create a free project and copy the connection string. The app accepts it as given
   (`postgresql://...?sslmode=require`) and converts it for the async driver.
2. **Ingest on your laptop** into a fresh index and the Neon database:
   ```bash
   cd backend
   DATABASE_URL='<neon url>' QDRANT_PATH=./deploy/qdrant uv run python -m app.cli ingest --dir ../data/pdfs --replace
   ./scripts/prepare_deploy.sh        # copies the two search models into deploy/models
   ```
3. **Google Cloud:** project with billing on the free trial (do not upgrade), a budget alert, then
   `gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com`.
4. **Deploy:**
   ```bash
   gcloud run deploy financial-insights-api --source backend --region asia-south1 \
     --memory 2Gi --cpu 1 --max-instances 1 --timeout 300 --allow-unauthenticated \
     --set-env-vars ENVIRONMENT=production,COOKIE_SAMESITE=none,CORS_ORIGINS='["https://<frontend>"]' \
     --set-env-vars DATABASE_URL='<neon url>',JWT_SECRET='<long random>',GROQ_API_KEY='<key>'
   ```
5. **Frontend:** set `VITE_API_URL` in Vercel to the service URL and redeploy.
6. **Check:** `/health` returns ok, `/docs` returns 404, sign in, ask a question.

`deploy/` is git-ignored: it holds the report index and models built on your machine.
