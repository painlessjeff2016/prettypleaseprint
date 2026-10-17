# AD5X conversion adapter — foundation only

This phase is isolated from PPP's application, database, and production Docker services.
Automatic upload conversion is **not yet active**.

## Setup

Use a pinned/reviewed copy of the MIT-licensed
[iChristGit/3MF-to-AD5X](https://github.com/iChristGit/3MF-to-AD5X)
engine. Place its `bambu2ad5x.py` at
`data/converter/engine/bambu2ad5x.py`.

Export an AD5X project from your own OrcaSlicer setup and save it as
`data/converter/templates/ad5x.3mf`. Do not commit personal profiles,
authentication tokens or machine passwords to Git.

Create `data/converter/work` and grant UID 65534 write permissions.
Put a model to test at `data/converter/work/input.3mf`.

Then run from the repository root:

```sh
docker compose -f docker-compose.3mf.yml build
docker compose -f docker-compose.3mf.yml run --rm converter
```

Expected outputs:
- `data/converter/work/result/converted.3mf`
- `data/converter/work/result/conversion.report.txt`

Each run needs a fresh result directory. Original input is left unchanged.
Open the resulting project in OrcaSlicer and inspect filament mapping, prime
tower, purge behavior, supports, and machine G-code **before printing**.

## Engineering notes

- Converter receives paths through argument arrays, never shell interpolation.
- Archive member count, expanded size and ratio are checked before conversion.
- Engine runs without network access and with a subprocess timeout.
- This standalone setup is for functional testing, not a production queue.
- Next phase: persistent Prisma conversion jobs, safe artifact storage, retry,
  admin-only downloads, and a post-commit enqueue hook in `src/lib/intake.ts`.
- The engine is mounted separately so PPP does not copy or change upstream code.
