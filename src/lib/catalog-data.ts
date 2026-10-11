import "server-only";

import { db } from "@/lib/db";
import type {
  CatalogMaterialChoice,
  CatalogColorChoice,
  ColorMode,
} from "@/lib/catalog";
import { listAvailableFilaments } from "@/lib/spoolman";

const useSpoolman = () => Boolean(process.env.SPOOLMAN_URL?.trim());

function spoolmanColor(
  filament: Awaited<ReturnType<typeof listAvailableFilaments>>[number],
): CatalogColorChoice {
  const whatever = filament.name === "Whatever's on";

  return {
    id: `spoolman:${filament.name}`,
    name: filament.name,
    hex: filament.hex,
    style: filament.hex,
    mode: (whatever ? "whatever" : "solid") as ColorMode,
  };
}

/** Available materials and colors for uploads and imports. */
export async function availableCatalog(): Promise<CatalogMaterialChoice[]> {
  if (useSpoolman()) {
    const filaments = await listAvailableFilaments();

    return [{
      id: "spoolman:PLA",
      name: "PLA",
      colors: filaments.map(spoolmanColor),
    }];
  }

  return db.catalogMaterial.findMany({
    where: { active: true, colors: { some: { active: true } } },
    orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
    select: {
      id: true,
      name: true,
      colors: {
        where: { active: true },
        orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
        select: {
          id: true,
          name: true,
          hex: true,
          style: true,
          mode: true,
        },
      },
    },
  });
}

/** Materials appearing in the catalog or existing print history. */
export async function knownMaterialNames(): Promise<string[]> {
  const [catalog, history] = await Promise.all([
    availableCatalog(),
    db.story.findMany({
      distinct: ["material"],
      select: { material: true },
    }),
  ]);

  return [...new Set([
    ...catalog.map((material) => material.name),
    ...history.map((story) => story.material),
  ])].sort((a, b) => a.localeCompare(b));
}

/** Authoritative server-side filament selection validation. */
export async function availableSelection(
  material: string,
  colorName: string,
): Promise<{ hex: string; style: string; mode: ColorMode } | null> {
  if (useSpoolman()) {
    if (material !== "PLA") return null;

    const filaments = await listAvailableFilaments();
    const filament = filaments.find((item) => item.name === colorName);

    if (!filament) return null;

    const color = spoolmanColor(filament);

    return {
      hex: color.hex,
      style: color.style,
      mode: color.mode,
    };
  }

  return db.catalogColor.findFirst({
    where: {
      active: true,
      name: colorName,
      material: { active: true, name: material },
    },
    select: { hex: true, style: true, mode: true },
  });
}
