/**
 * Just enough CBOR for WebAuthn: attestation objects and COSE keys are
 * definite-length maps, arrays, byte strings, text strings and integers.
 * No other CBOR feature is needed, and unsupported input fails loudly.
 */

export type CborValue =
  | number
  | string
  | boolean
  | null
  | Buffer
  | CborValue[]
  | Map<number | string, CborValue>;

export function decodeCbor(buffer: Buffer, start = 0): { value: CborValue; offset: number } {
  if (start >= buffer.length) throw new Error("CBOR ended early.");
  const initial = buffer[start];
  let offset = start + 1;
  const major = initial >> 5;
  const info = initial & 0x1f;

  const length = (): number => {
    if (info < 24) return info;
    if (info === 24) {
      const value = buffer[offset];
      offset += 1;
      return value;
    }
    if (info === 25) {
      const value = buffer.readUInt16BE(offset);
      offset += 2;
      return value;
    }
    if (info === 26) {
      const value = buffer.readUInt32BE(offset);
      offset += 4;
      return value;
    }
    if (info === 27) {
      const value = Number(buffer.readBigUInt64BE(offset));
      offset += 8;
      return value;
    }
    throw new Error("Indefinite-length CBOR is not supported here.");
  };

  switch (major) {
    case 0:
      return { value: length(), offset };
    case 1:
      return { value: -1 - length(), offset };
    case 2: {
      const size = length();
      const value = buffer.subarray(offset, offset + size);
      return { value, offset: offset + size };
    }
    case 3: {
      const size = length();
      const value = buffer.subarray(offset, offset + size).toString("utf8");
      return { value, offset: offset + size };
    }
    case 4: {
      const size = length();
      const value: CborValue[] = [];
      for (let index = 0; index < size; index += 1) {
        const item = decodeCbor(buffer, offset);
        value.push(item.value);
        offset = item.offset;
      }
      return { value, offset };
    }
    case 5: {
      const size = length();
      const map = new Map<number | string, CborValue>();
      for (let index = 0; index < size; index += 1) {
        const key = decodeCbor(buffer, offset);
        offset = key.offset;
        const item = decodeCbor(buffer, offset);
        offset = item.offset;
        if (typeof key.value === "number" || typeof key.value === "string") {
          map.set(key.value, item.value);
        }
      }
      return { value: map, offset };
    }
    case 7:
      if (info === 20) return { value: false, offset };
      if (info === 21) return { value: true, offset };
      if (info === 22) return { value: null, offset };
      throw new Error("Unsupported CBOR simple value.");
    default:
      throw new Error(`Unsupported CBOR major type ${major}.`);
  }
}

export function decodeCborFirst(buffer: Buffer): CborValue {
  return decodeCbor(buffer).value;
}
