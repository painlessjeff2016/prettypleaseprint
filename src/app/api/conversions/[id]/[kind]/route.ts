import { NextResponse } from "next/server";
import { Readable } from "node:stream";
import { currentUser, storyRef } from "@/lib/authz";
import { db } from "@/lib/db";
import { openModel } from "@/lib/storage";
import { record } from "@/lib/audit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Admin-only retrieval of generated AD5X project and conversion report. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string; kind: string }> },
) {
  const { id, kind } = await params;
  const storyId = Number(id);
  const user = await currentUser();
  if (!user) return new NextResponse(null, { status: 401 });
  // Unlike the original model's route, converted artifacts are admin-only.
  if (user.role !== "admin") return new NextResponse(null, { status: 404 });
  if (!Number.isSafeInteger(storyId) || storyId <= 0 ||
      (kind !== "model" && kind !== "report")) {
    return new NextResponse(null, { status: 404 });
  }

  const conversion = await db.modelConversion.findUnique({
    where: { storyId },
    select: { status: true, outputStorageKey: true, reportStorageKey: true },
  });
  if (!conversion || conversion.status !== "completed") {
    return new NextResponse(null, { status: 404 });
  }

  const key = kind === "model"
    ? conversion.outputStorageKey
    : conversion.reportStorageKey;
  if (!key) return new NextResponse(null, { status: 404 });

  let file;
  try {
    file = await openModel(key);
  } catch (error) {
    console.error("[ad5x] artifact read failed", error);
    return new NextResponse(null, { status: 502 });
  }
  if (!file) return new NextResponse(null, { status: 502 });

  await record({
    action: "conversion.downloaded",
    actor: user,
    subject: storyRef(storyId),
    detail: { kind },
  });

  const filename = kind === "model"
    ? `${storyRef(storyId)}_AD5X.3mf`
    : `${storyRef(storyId)}_AD5X.report.txt`;

  return new NextResponse(Readable.toWeb(file.stream) as ReadableStream<Uint8Array>, {
    headers: {
      "content-type": kind === "model" ? "model/3mf" : "text/plain; charset=utf-8",
      "content-length": String(file.size),
      "content-disposition": `attachment; filename="${filename}"`,
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
