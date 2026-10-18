# AD5X conversion adapter — foundation only

This phase is isolated from PPP's application, database, and production Docker services.
Automatic upload conversion is **not yet active**.

## Setup (built-in AD5X defaults)

Use a pinned/reviewed copy of the MIT-licensed
[iChristGit/3MF-to-AD5X](https://github.com/iChristGit/3MF-to-AD5X)
engine. Place its `bambu2ad5x.py` at
`data/converter/engine/bambu2ad5x.py`.

Also place the engine's bundled `ad5x_template.json` next to `bambu2ad5x.py`.
These are the program's unmodified default printer settings.
Do not commit personal profiles, authentication tokens or passwords to Git.

Create `data/converter/work` and grant UID 65534 write permissions.
Put a model to test at `data/converter/work/input.3mf`.

Then run from the repository root:

```sh
docker compose -p ppp-3mf -f docker-compose.3mf.yml build converter
docker compose -p ppp-3mf -f docker-compose.3mf.yml run --rm converter
```

Expected outputs:
- `data/converter/work/result/converted.3mf`
- `data/converter/work/result/conversion.report.txt`

Each run needs a fresh result directory. Original input is left unchanged.
The adapter copies output from Docker's `/tmp` tmpfs into a staging
directory *inside* `/work/result` before atomically renaming the two
artifacts. That avoids Linux EXDEV ("Invalid cross-device link") errors.
After changing the adapter, **rebuild** the image before rerunning.
The `-p ppp-3mf` flag avoids treating production PPP containers as orphans;
do not use `--remove-orphans` with the regular PPP Compose project.
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
