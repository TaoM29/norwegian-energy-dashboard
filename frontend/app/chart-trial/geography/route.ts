import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-static";

export async function GET() {
  const source = path.join(process.cwd(), "..", "data", "file.geojson");
  const geography = await readFile(source, "utf8");

  return new Response(geography, {
    headers: {
      "Content-Type": "application/geo+json",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
