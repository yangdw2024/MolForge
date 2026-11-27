import { describe, expect, it } from "vitest";
import { decodeBinaryMolecule } from "../src/services/api";

describe("MOLF Binary Molecule Protocol Decoder", () => {
  it("decodes valid MOLF binary stream including unit cell matrix", () => {
    // 2 atoms, 1 bond, revision=5, hasCell=1
    // sizes: header 32 + coords 24 + z(2+2pad=4) + vdw 8 + rgba 8 + pairs 8 + bo(1+3pad=4) + cell(12+36=48) = 136 bytes
    const buf = new ArrayBuffer(136);
    const dv = new DataView(buf);
    dv.setUint32(0, 0x4d4f4c46, true); // MAGIC_MOLF
    dv.setUint32(4, 1, true);
    dv.setUint32(8, 2, true); // numAtoms
    dv.setUint32(12, 1, true); // numBonds
    dv.setUint32(16, 5, true); // revision
    dv.setUint32(20, 1, true); // hasCell

    // Coords at offset 32: atom0=(0,0,0), atom1=(1.2,0,0)
    dv.setFloat32(32 + 12, 1.2, true);
    // atomicNumbers at offset 56
    new Uint8Array(buf, 56, 2).set([8, 8]);
    // vdwRadii at offset 60
    dv.setFloat32(60, 1.52, true);
    dv.setFloat32(64, 1.52, true);
    // rgba at offset 68
    new Uint8Array(buf, 68, 8).set([255, 40, 40, 255, 255, 40, 40, 255]);
    // bondPairs at offset 76
    new Uint32Array(buf, 76, 2).set([0, 1]);
    // bondOrders at offset 84
    new Uint8Array(buf, 84, 1).set([2]);
    // cell boxOrigin (88) + cellMatrix (100)
    dv.setFloat32(100, 10, true);
    dv.setFloat32(116, 10, true);
    dv.setFloat32(132, 10, true);

    const decoded = decodeBinaryMolecule(buf);
    expect(decoded.numAtoms).toBe(2);
    expect(decoded.numBonds).toBe(1);
    expect(decoded.revision).toBe(5);
    expect(decoded.hasCell).toBe(true);
    expect(decoded.coords[3]).toBeCloseTo(1.2, 4);
    expect(decoded.bondOrders[0]).toBe(2);
    expect(decoded.boundingRadius).toBeGreaterThan(5);
  });

  it("rejects invalid binary magic header", () => {
    const bad = new ArrayBuffer(32);
    expect(() => decodeBinaryMolecule(bad)).toThrow(/Invalid MolForge binary stream magic/);
  });
});
