/**
 * Durable, single-process AD5X conversion worker.
 *
 * Polls Prisma for 3MF conversion jobs. The story and the original upload
 * are never changed. A job is claimed by an atomic conditional update,
 * allowing safe contention if two workers happen to run.
 */
import { execFile } from "node:child_process";
import { mkdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { PrismaClient } from "@prisma/client";

const execFileAsync = promisify(execFile);
const db = new PrismaClient();
const root = path.resolve(process.env.MODELS_ROOT ?? "/uploads");
const engine = "/engine/bambu2ad5x.py";
const staleAfterMs = 15 * 60 * 1000;
const pollMs = 5000;
let stopping = false;

process.on("SIGTERM", () => { stopping = true; });
process.on("SIGINT", () => { stopping = true; });

function safePath(key: string): string {
  const full = path.resolve(root, key);
  if (!full.startsWith(root + path.sep)) {
    throw new Error("Storage key escapes model root");
  }
  return full;
}

async function claimJob() {
  const eligibility = () => ({
    OR: [
      { status: "pending" },
      { status: "processing", startedAt: { lt: new Date(Date.now() - staleAfterMs) } },
    ],
  });
  const candidate = await db.modelConversion.findFirst({
    where: eligibility(),
    orderBy: { createdAt: "asc" },
    select: { id: true, storyId: true },
  });
  if (!candidate) return null;

  // Claim only if status hasn't changed since we read the candidate.
  // updateMany returns count=0 if a competing worker already claimed it.
  const acquired = await db.modelConversion.updateMany({
    where: { id: candidate.id, ...eligibility() },
    data: {
      status: "processing",
      attempts: { increment: 1 },
      startedAt: new Date(),
      completedAt: null,
      errorMessage: null,
      outputStorageKey: null,
      reportStorageKey: null,
    },
  });
  return acquired.count === 1 ? candidate : null;
}

async function runJob(job: { id: string; storyId: number }) {
  if (!/^[a-z0-9]+$/.test(job.id) || !Number.isSafeInteger(job.storyId) || job.storyId <= 0) {
    throw new Error("Invalid conversion job identifier");
  }
  const story = await db.story.findUnique({
    where: { id: job.storyId },
    select: { storageKey: true, filename: true },
  });
  if (!story || !/^models\/\d{4}-\d{2}\/[0-9a-f-]{36}\.3mf$/.test(story.storageKey)) {
    throw new Error("Original 3MF storage key is unavailable or invalid");
  }

  const relative = `conversions/${job.storyId}/${job.id}`;
  const source = safePath(story.storageKey);
  const destination = safePath(relative);
  // Only this job's derived output directory is removed, never source bytes.
  // Handles a stale job where the output was written but DB update was lost.
  await rm(destination, { recursive: true, force: true });
  await mkdir(destination, { recursive: true, mode: 0o755 });

  await execFileAsync("python3", [
    "/app/convert.py", source, destination, "--engine", engine, "--timeout", "180",
  ], {
    timeout: 210000,
    maxBuffer: 1024 * 1024,
    // Do not pass the Prisma worker's DATABASE_URL or any application secrets
    // to the third-party Python conversion engine.
    env: {
      PATH: process.env.PATH ?? "/usr/local/bin:/usr/bin:/bin",
      TMPDIR: "/tmp",
      PYTHONDONTWRITEBYTECODE: "1",
    },
  });

  const convertedKey = `${relative}/converted.3mf`;
  const reportKey = `${relative}/conversion.report.txt`;
  const [converted, report] = await Promise.all([
    stat(safePath(convertedKey)),
    stat(safePath(reportKey)),
  ]);
  if (!converted.isFile() || converted.size === 0 || !report.isFile()) {
    throw new Error("Conversion did not produce valid artifacts");
  }

  await db.modelConversion.update({
    where: { id: job.id },
    data: {
      status: "completed",
      completedAt: new Date(),
      errorMessage: null,
      outputStorageKey: convertedKey,
      reportStorageKey: reportKey,
    },
  });
  console.info(`[ad5x] converted story ${job.storyId}`);
}

async function main() {
  console.info("[ad5x] conversion worker started");
  while (!stopping) {
    try {
      const job = await claimJob();
      if (job) {
        try {
          await runJob(job);
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          console.error(`[ad5x] story ${job.storyId} failed: ${message}`);
          // If a ticket was withdrawn during conversion, its DB row has
          // cascaded away; remove any output written after withdrawal.
          // Also clean up partial output from ordinary conversion failures.
          try {
            if (/^[a-z0-9]+$/.test(job.id) && Number.isSafeInteger(job.storyId) && job.storyId > 0) {
              await rm(safePath(`conversions/${job.storyId}/${job.id}`), {
                recursive: true, force: true,
              });
            }
          } catch (cleanupError) {
            console.error("[ad5x] couldn't clean partial artifacts", cleanupError);
          }
          try {
            await db.modelConversion.update({
              where: { id: job.id },
              data: { status: "failed", completedAt: new Date(), errorMessage: message.slice(0, 1000) },
            });
          } catch (dbError) {
            // A temporary DB outage leaves "processing" for stale-job recovery.
            console.error("[ad5x] couldn't persist failure", dbError);
          }
        }
        continue;
      }
    } catch (error) {
      console.error("[ad5x] queue poll failed", error);
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
  await db.$disconnect();
}

main().catch(async (error) => {
  console.error("[ad5x] fatal error", error);
  await db.$disconnect();
  process.exitCode = 1;
});
