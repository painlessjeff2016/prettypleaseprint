# Automatic AD5X/HueForge conversion (opt-in)

PPP can automatically create a **second, derived AD5X 3MF project** for
newly uploaded or imported 3MF print requests. The original file is never
replaced or edited. Existing STL and OBJ behavior is unchanged.

**Safety/status:** feature branch, draft PR, not a production release.
Before enabling this on your existing PPP, test it against a disposable
Postgres/PPP stack. The new DB migration is additive but has not been
validated against your production database. No production deployment or
migration has been performed by this work.

## Converter version and printer profile

The worker image bundles the exact **reviewed commit** of
[painlessjeff2016/3MF-to-AD5X](https://github.com/painlessjeff2016/3MF-to-AD5X):

`fc4042038059d501540ee16f2d03991e4c5a92b3`

This commit contains the HueForge fix that understands per-layer
`tool_change` commands without pruning referenced filament slots. It also
contains the owner's complete AD5X/ZMOD template:
`LED_ON` + `START_PRINT` at print start,
`END_PRINT` + `LED_OFF` at print end, and
`SET_PRINT_STATS_INFO` before each layer.

`services/3mf-converter/fetch-engine.py` checks SHA-256 of the script,
template and MIT license **during image build**. No internet download,
GitHub credentials or writable engine mount is needed at runtime.
A future converter update requires reviewing the commit and checksums
together. The worker image is published alongside PPP's other images
as `ppp-ad5x-worker` via `.github/workflows/release-images.yml`.

This pinned converter still uses generic Flashforge presets by material
type, not an exact mapping of every uploader's installed Spoolman presets.
Color slots and layer tool changes survive; physical IFS spool assignments
are a separate task. More than four colors require manual planning for
the AD5X's four active IFS slots. **Do not automatically start prints
from converted projects.** Verify them in OrcaSlicer first.

## Pipeline

1. `src/lib/intake.ts` creates a pending `ModelConversion` together with
   each accepted 3MF request when `AD5X_AUTOCONVERT=true`.
   Requeuing a 3MF can create a new job. No historical backfill.
2. `scripts/3mf-worker.ts` claims jobs atomically via Prisma. It runs
   `services/3mf-converter/convert.py` as a separate Python subprocess.
   A minimal child environment deliberately excludes `DATABASE_URL`.
3. The adapter validates ZIP limits, invokes the pinned converter with
   `--report`, checks the result, and publishes the derived project and
   report into a job-specific folder on the uploads volume.
4. The worker records `completed` / `failed`. The original file remains
   attached to the story, and only the admin sees the status and download
   links on `/story/{id}`. The download endpoints check admin auth.
5. The worker can reclaim stale `processing` jobs after 15 minutes.
   There is no automatic retry of ordinary conversion failures and
   no historical backfill. Withdrawn stories remove derived output.

## Local tests (no production DB)

Adapter tests (the engine-dependent tests skip when no engine path is set):

```sh
python3 -m unittest discover -s services/3mf-converter -p 'test_*.py' -v
```

Fetch the verified engine and run its full five-color regression test:

```sh
python3 services/3mf-converter/fetch-engine.py /tmp/ppp-ad5x-engine
AD5X_ENGINE_DIR=/tmp/ppp-ad5x-engine \
  python3 -m unittest discover -s services/3mf-converter -p 'test_*.py' -v
```

For your real HueForge **original** (never the old broken `_AD5X`):

```sh
AD5X_ENGINE_DIR=/tmp/ppp-ad5x-engine \
HUEFORGE_SAMPLE="$HOME/Downloads/3D Prints/RDR_Front_229x256.3mf" \
  python3 -m unittest discover -s services/3mf-converter -p 'test_*.py' -v
```

Validate app types and Prisma without a live database:

```sh
npm ci
DATABASE_URL=postgresql://test:test@localhost:5432/test npx prisma validate
npx prisma generate
npx tsc --noEmit
```

The additive migration lives under
`prisma/migrations/20261018023000_ad5x_conversion`.
Never run it against production as the first integration test.

## Container build and staging

PPP normally deploys **published images**, not a source checkout. The
optional overlay `docker-compose.ad5x.yml` adds the conversion worker
and enables queuing on the app. It does not change anything unless included
in the active Compose command. It shares the normal `/uploads` mount,
joins a private network with Postgres and exposes no extra ports.

From a source checkout and a **test-only** `.env.docker` / `DATA_ROOT`:

```sh
docker compose --env-file .env.docker \
  -f docker-compose.prod.yml -f docker-compose.build.yml \
  -f docker-compose.ad5x.yml config

docker compose --env-file .env.docker \
  -f docker-compose.prod.yml -f docker-compose.build.yml \
  -f docker-compose.ad5x.yml up -d --build
```

On a host using published `ppp-app`, `ppp-migrate` and
`ppp-ad5x-worker` images from the same commit/tag:

```sh
docker compose --env-file .env.docker \
  -f docker-compose.prod.yml -f docker-compose.ad5x.yml up -d
```

**Use published images containing this feature**, not older PPP images
that don't have the queue model or migration. The release workflow
publishes the worker only after the feature is merged to `main`.
For staging, set `PPP_REGISTRY` and `PPP_TAG` appropriately.

Check `docker compose ... logs --tail=100 ad5x-worker` and upload a test
3MF. Confirm `pending → processing → completed`, download the generated
project from the admin ticket, then open it with **File → Open Project** in
OrcaSlicer. Inspect all colors, print settings, purge behavior, prime tower,
filament assignments and G-code before any real print.

## Limitations and rollback

- Converted assets are admin-only; requesters only receive the original.
- More than four filament colors cannot all be loaded simultaneously
  into the AD5X IFS; plan a physical swap or separate plates.
- Engine subprocess timeouts and ZIP/archive limits may reject large
  but otherwise valid projects; failed conversions do not block uploads.
- Failed jobs are recorded, not silently discarded; there is no manual
  retry UI or orphan-reconciliation process.
- To disable conversion, stop `ad5x-worker` and redeploy the app without
  the overlay. **Do not remove Docker volumes or the new database table**
  as part of a rollback. The original uploaded 3MFs remain untouched.
- Never deploy this feature in the middle of a live print or while
  intoxicated. Test in staging first.
