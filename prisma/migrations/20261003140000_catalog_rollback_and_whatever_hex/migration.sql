-- Two corrections to the catalogue migrations before them, written as a new
-- migration rather than as edits so a database that has already applied those
-- ends up in the same place as one that has not.

-- 1. Put the "Material" type back.
--
-- `story.material` is text now and nothing in this schema uses the enum. The
-- previous image's Prisma client still does: it casts every insert to
-- "Material", and with the type dropped each upload fails with
--   type "public.Material" does not exist
-- while pages go on rendering. The deploy wizard rolls back to that image when
-- a deploy fails its health check, so dropping the type turned a failed deploy
-- into a rollback where nobody can file a request. An enum value assigns into
-- a text column, so the type existing is all the old client needs.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'Material') THEN
    CREATE TYPE "Material" AS ENUM ('PLA', 'PETG', 'TPU', 'Resin');
  END IF;
END
$$;

-- 2. "Whatever" keeps the neutral grey as its representative colour.
--
-- `colorHex` is what the 3D viewer paints the model with and what the audit
-- page tallies. The gradient migration changed it from #b6bcc2 to #7557c7 on
-- every existing "Whatever's on" ticket, which rewrote old tickets — the one
-- thing the snapshots exist to prevent — and turned a model whose colour is
-- by definition unknown purple. The rainbow lives in `colorStyle`; the
-- representative colour goes back to what those tickets were filed with.
UPDATE "story" SET "colorHex" = '#b6bcc2' WHERE "colorMode" = 'whatever';
UPDATE "catalogColor" SET "hex" = '#b6bcc2' WHERE "mode" = 'whatever';
