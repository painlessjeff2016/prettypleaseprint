-- Additive conversion tracking: existing print requests remain unchanged.
-- One job per story; deleting a story cascades to its job metadata.
CREATE TABLE "modelConversion" (
    "id" TEXT NOT NULL,
    "storyId" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "outputStorageKey" TEXT,
    "reportStorageKey" TEXT,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "startedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "modelConversion_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "modelConversion_storyId_key" ON "modelConversion"("storyId");
CREATE INDEX "modelConversion_status_createdAt_idx" ON "modelConversion"("status","createdAt");

ALTER TABLE "modelConversion"
ADD CONSTRAINT "modelConversion_storyId_fkey"
FOREIGN KEY ("storyId") REFERENCES "story"("id") ON DELETE CASCADE ON UPDATE CASCADE;
