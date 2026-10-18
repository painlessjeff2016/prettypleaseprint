# Automatic AD5X project conversion (opt-in)

This feature automatically creates an **additional** Flashforge AD5X project for new
3MF print requests, including files imported from Printables and requeued requests. Originals remain
attached to their requests. STL/OBJ requests are unchanged.

The default upstream AD5X machine profile (`ad5x_template.json`) is used.
The converter generates a text report. Only the PPP administrator can see
conversion status, converted project and report links on the ticket page.

**Development status:** this integration has not yet been confirmed by a full
PPP upload test. Validate on a non-production database before deployment.

## How the pipeline works

1. `src/lib/intake.ts` writes the original into `MODELS_ROOT` and creates
   the print request plus a pending `ModelConversion` in one DB operation.
   The gate is `AD5X_AUTOCONVERT=true`.
2. `scripts/3mf-worker.ts` polls Postgres, atomically claims a job, and runs
   the Python adapter without shell interpolation.
3. The Python adapter validates ZIP structure/limits, invokes
   `bambu2ad5x.py --output ... --report` with bundled AD5X defaults, checks
   the output, stages files on the upload filesystem and publishes them.
4. The worker checks both artifacts, records their generated storage keys and
   marks the job completed (or failed). The original is never modified.
5. The admin sees status and download links at `/story/{id}`.
   `/api/conversions/{id}/model` and `/api/conversions/{id}/report`
   both enforce session/admin authentication server-side.

Interrupted `processing` jobs can be reclaimed after 15 minutes (the subprocess
has a 180-second internal timeout). Failed jobs remain visible for diagnosis.
Existing tickets are not backfilled, and manual retry isn't implemented yet.

## On a Debian development checkout

First run the existing isolated adapter tests:

```sh
python3 -m unittest discover -s services/3mf-converter -p 'test_*.py' -v
```

Validate the schema and TypeScript build without touching a live database:

```sh
DATABASE_URL=postgresql://test:test@localhost:5432/test npx prisma validate
npx prisma generate
npm run build
```

The migration in `prisma/migrations/20261018023000_ad5x_conversion` is
additive; it creates a new job table and doesn't rewrite existing stories.

For an integration test, use a test instance of PPP/Postgres and create a new
3MF print request after enabling the overlay. Confirm that status progresses
`pending → processing → completed`, then open the resulting 3MF in OrcaSlicer
via **File → Open Project**. Inspect painting, filament mapping, purge settings,
prime tower placement and G-code before printing.

## Opt-in Docker deployment

The **additional** `docker-compose.ad5x.yml` overlay enables the app's enqueue
flag and starts the worker together. Without this overlay, behavior remains
unchanged. Don't add the overlay before the engine and database migration are
ready.

On the Docker host, identify the actual `DATA_ROOT` set in `.env.docker`.
Put the converter's two reviewed, version-matched upstream files in
`${DATA_ROOT}/converter/engine/`:

```text
converter/engine/
  bambu2ad5x.py
  ad5x_template.json
```

Keep these files outside Git and treat updates to the upstream engine as a
separate reviewed change. The worker never downloads code at runtime.

The worker operates as numeric UID/GID 1001:1001 (same as PPP's Next.js app).
The migrator prepares `${DATA_ROOT}/uploads` for that UID. Both containers
share this mount. The worker connects to Postgres only through an internal
Docker network and exposes no ports. The Python conversion subprocess receives
a minimal environment without the worker's DATABASE_URL (defense-in-depth).

For a staging instance with `.env.docker` configured for **staging**:

```sh
docker compose --env-file .env.docker \
  -f docker-compose.prod.yml -f docker-compose.build.yml \
  -f docker-compose.ad5x.yml config

docker compose --env-file .env.docker \
  -f docker-compose.prod.yml -f docker-compose.build.yml \
  -f docker-compose.ad5x.yml up -d --build

docker compose --env-file .env.docker \
  -f docker-compose.prod.yml -f docker-compose.build.yml \
  -f docker-compose.ad5x.yml logs --tail=100 ad5x-worker
```

This uses the normal PPP Compose project (unlike the standalone test service's
`-p ppp-3mf`). Never use `--remove-orphans` to fix warnings.

## Rollback and operational limitations

- **Disable new conversion jobs:** stop the worker using the full Compose file
  stack with `docker compose ... -f docker-compose.ad5x.yml stop ad5x-worker`,
  then redeploy PPP without the overlay. Existing files and job rows are
  retained; no original model is modified. Do not remove orphan containers
  indiscriminately.
- **Do not roll back the migration:** it is additive and the older app simply
  ignores the new table. Keep migration/DB compatible with PPP's release wizard.
- **Admin only:** converted assets are not sent to requesters automatically.
- **No backfill:** previously uploaded 3MFs get no conversion job.
- **Cleanup:** withdrawing a ticket removes its original file and its
  generated conversion directory. A failed in-flight job also removes partial
  output. A separate periodic orphan-file sweep is not implemented yet.
- **No retries yet:** invalid/unsupported files show `failed`; recovery of
  interrupted jobs uses a 15-minute staleness threshold.
- **Engine prerequisites:** a missing upstream engine or its default template
  causes visible conversion failure; ordinary uploads still succeed.
- **Secrets:** don't commit `.env.docker`, per-printer auth material, or
  production model files.

## Known deployment follow-up

The worker image currently builds from the repository's `Dockerfile`. For a
remote Docker host running PPP from only prebuilt images (without a Git
checkout), the worker will also need a published image and corresponding CI /
deployment-wizard integration. **Do not point the production wizard at this
overlay until that packaging has been tested.**
