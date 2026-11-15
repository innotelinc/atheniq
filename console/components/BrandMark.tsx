import type { BrandSettings } from "@/lib/types";
import { monogram } from "@/lib/branding";

/** Logo placement: an image when one is set, otherwise a monogram badge. */
export function BrandMark({ brand, size = 36 }: { brand: BrandSettings; size?: number }) {
  if (brand.logoUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        className="brand-logo"
        src={brand.logoUrl}
        alt={`${brand.siteName} logo`}
        style={{ maxHeight: size, width: "auto", display: "block" }}
      />
    );
  }
  return (
    <span
      className="brand-badge"
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
    >
      {monogram(brand)}
    </span>
  );
}
