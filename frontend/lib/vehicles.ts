/** Vehicle model NAMES only (mirrors backend/app/vehicles.py) for filename pre-fill. No specs. */
export const VEHICLE_ALIASES: Record<string, string[]> = {
  Alcazar: ["alcazar", "alcazr", "alkazar"],
  Creta: ["creta", "kreta"],
  i20: ["i20", "i-20", "i 20"],
  Aura: ["aura"],
  Venue: ["venue"],
  Verna: ["verna"],
  Exter: ["exter"],
  "Grand i10 Nios": ["grand i10 nios", "i10 nios", "nios", "grand i10"],
  Tucson: ["tucson"],
  "Ioniq 5": ["ioniq 5", "ioniq5", "ioniq"],
  "Kona Electric": ["kona"],
};

export function detectVehicleFromFilename(filename: string): string | null {
  const stem = filename
    .replace(/\.pdf$/i, "")
    .replace(/[_\-.]+/g, " ")
    .toLowerCase();
  let best: { model: string; len: number } | null = null;
  for (const [model, aliases] of Object.entries(VEHICLE_ALIASES)) {
    for (const alias of aliases) {
      const re = new RegExp(`(^|[^a-z0-9])${alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^a-z0-9])`);
      if (re.test(stem) && (!best || alias.length > best.len)) best = { model, len: alias.length };
    }
  }
  return best?.model ?? null;
}
