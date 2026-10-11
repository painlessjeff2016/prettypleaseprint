import "server-only";

export type FilamentChoice = {
  name: string;
  hex: string;
  material: "PLA";
  filamentIds: number[];
};

type Spool = {
  id: number;
  archived: boolean;
  remaining_weight: number | null;
  filament: {
    id: number;
    name: string;
    material: string;
    color_hex: string | null;
  };
};

export const WHATEVER_FILAMENT: FilamentChoice = {
  name: "Whatever's on",
  hex: "#b6bcc2",
  material: "PLA",
  filamentIds: [],
};

const CACHE_MS = 60_000;

let cache: FilamentChoice[] | null = null;
let cacheUntil = 0;
let pending: Promise<FilamentChoice[]> | null = null;

function normalizeHex(value: string | null): string {
  const hex = (value ?? "").replace(/^#/, "").trim();

  return /^[0-9a-fA-F]{6}$/.test(hex)
    ? `#${hex.toUpperCase()}`
    : "#B6BCC2";
}

function describeFilament(rawName: string): string {
  const name = rawName.trim();

  const variants = [
    { pattern: /^silk\+\s+/i, label: "Silk+" },
    { pattern: /^silk\s+/i, label: "Silk" },
    { pattern: /^matte\s+/i, label: "Matte" },
    { pattern: /^marble\s+/i, label: "Marble" },
    { pattern: /^basic\s+/i, label: "Basic" },
  ];

  for (const variant of variants) {
    if (variant.pattern.test(name)) {
      const color = name.replace(variant.pattern, "").trim();
      return `${variant.label} PLA – ${color}`;
    }
  }

  return `Basic PLA – ${name}`;
}

async function fetchInventory(): Promise<FilamentChoice[]> {
  const base = process.env.SPOOLMAN_URL?.replace(/\/+$/, "");

  if (!base) {
    throw new Error("SPOOLMAN_URL is not configured");
  }

  const response = await fetch(`${base}/api/v1/spool`, {
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  });

  if (!response.ok) {
    throw new Error(`Spoolman returned HTTP ${response.status}`);
  }

  const data: unknown = await response.json();

  if (!Array.isArray(data)) {
    throw new Error("Unexpected Spoolman response");
  }

  const choices = new Map<string, FilamentChoice>();

  for (const spool of data as Spool[]) {
    if (
      spool.archived ||
      typeof spool.remaining_weight !== "number" ||
      spool.remaining_weight <= 0 ||
      spool.filament?.material?.toUpperCase() !== "PLA" ||
      !spool.filament.name?.trim()
    ) {
      continue;
    }

    const name = describeFilament(spool.filament.name);
    const hex = normalizeHex(spool.filament.color_hex);

    const existing = choices.get(name);

    if (existing) {
      if (!existing.filamentIds.includes(spool.filament.id)) {
        existing.filamentIds.push(spool.filament.id);
      }
    } else {
      choices.set(name, {
        name,
        hex,
        material: "PLA",
        filamentIds: [spool.filament.id],
      });
    }
  }

  return [
    ...Array.from(choices.values()).sort((a, b) =>
      a.name.localeCompare(b.name),
    ),
    WHATEVER_FILAMENT,
  ];
}

export async function listAvailableFilaments(): Promise<FilamentChoice[]> {
  if (cache && Date.now() < cacheUntil) {
    return cache;
  }

  if (!pending) {
    pending = fetchInventory()
      .then((result) => {
        cache = result;
        cacheUntil = Date.now() + CACHE_MS;
        return result;
      })
      .catch((error) => {
        console.error("[spoolman] inventory refresh failed:", error);

        // Keep the last known inventory during temporary outages.
        // On a cold start, only the independent fallback is available.
        cacheUntil = Date.now() + CACHE_MS;
        return cache ?? [WHATEVER_FILAMENT];
      })
      .finally(() => {
        pending = null;
      });
  }

  return pending;
}

export async function findAvailableFilament(
  name: string,
): Promise<FilamentChoice | undefined> {
  const choices = await listAvailableFilaments();
  return choices.find((choice) => choice.name === name);
}
