import * as THREE from "three";
import { makePhysicalFrame } from "./scene.js";

// Esta clase dibuja la GEOMETRÍA VISUAL a partir de los mismos números (SI) que usa el backend
// para el modelo físico. La cámara de vacío es mayor que los dees (margen visual); las paredes
// físicas del modelo son: radio R de los dees (extracción) y |z| = H/2 (pérdida).
const COLORS = {
  chamber: 0x6aa9ff, deeRight: 0x18c29c, deeLeft: 0xd946ef, gap: 0xffd54a,
  source: 0xe5e7eb, bField: 0xc77dff, eField: 0xffd54a,
};
const CHAMBER_MARGIN = 1.12;     // radio de la cámara = 1.12 R (solo visual)
const CHAMBER_HEIGHT_FACTOR = 1.3;

function translucent(color, opacity) {
  return new THREE.MeshBasicMaterial({
    color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false,
  });
}

function outline(geometry, color, opacity = 0.85) {
  return new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 25),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
  );
}

export class CyclotronView {
  constructor(scene) {
    this.scene = scene;
    this.frame = null;
    this.opacity = { chamber: 0.10, dees: 0.28 };
    this.fieldVectorsVisible = true;
    this.chamberMats = [];
    this.deeMats = [];
    this.fieldGroup = null;
    this.eArrows = [];
    this.eMaxLength = 0;
  }

  /** Reconstruye toda la geometría. geometry = {dee_radius_m, gap_m, height_m}. */
  build(geometry, bSign, hasElectric) {
    this.dispose();
    const R = geometry.dee_radius_m, g = geometry.gap_m, H = geometry.height_m;
    const frame = makePhysicalFrame();      // dentro de este grupo: coordenadas físicas en metros

    // ---- Cámara de vacío (cilindro translúcido con eje z) ----
    const Rc = R * CHAMBER_MARGIN, Hc = H * CHAMBER_HEIGHT_FACTOR;
    const chamberGeo = new THREE.CylinderGeometry(Rc, Rc, Hc, 96, 1, false);
    chamberGeo.rotateX(Math.PI / 2);        // eje del cilindro: y → z
    const chamberMat = translucent(COLORS.chamber, this.opacity.chamber);
    const chamberEdges = outline(chamberGeo, COLORS.chamber, 0.5);
    frame.add(new THREE.Mesh(chamberGeo, chamberMat), chamberEdges);
    this.chamberMats = [chamberMat];

    // ---- Dees: semidiscos de radio R con borde recto en x = ±g/2, extruidos en z ----
    const thetaMax = Math.acos(g / (2 * R));
    const makeDee = (side) => {
      const shape = new THREE.Shape();
      if (side > 0) shape.absarc(0, 0, R, -thetaMax, thetaMax, false);
      else shape.absarc(0, 0, R, Math.PI - thetaMax, Math.PI + thetaMax, false);
      const geo = new THREE.ExtrudeGeometry(shape, { depth: H, bevelEnabled: false, curveSegments: 64 });
      geo.translate(0, 0, -H / 2);
      const color = side > 0 ? COLORS.deeRight : COLORS.deeLeft;
      const mat = translucent(color, this.opacity.dees);
      frame.add(new THREE.Mesh(geo, mat), outline(geo, color));
      return mat;
    };
    this.deeMats = [makeDee(+1), makeDee(-1)];

    // ---- Región de aceleración eléctrica: franja |x| ≤ g/2 ----
    const yb = Math.sqrt(R * R - (g / 2) ** 2);
    const gapShape = new THREE.Shape();
    gapShape.moveTo(-g / 2, -yb); gapShape.lineTo(g / 2, -yb);
    gapShape.lineTo(g / 2, yb); gapShape.lineTo(-g / 2, yb);
    const gapGeo = new THREE.ExtrudeGeometry(gapShape, { depth: H, bevelEnabled: false });
    gapGeo.translate(0, 0, -H / 2);
    const gapMat = translucent(COLORS.gap, 0.22);
    frame.add(new THREE.Mesh(gapGeo, gapMat), outline(gapGeo, COLORS.gap, 0.9));
    this.gapMat = gapMat;

    // ---- Fuente de partículas (anillo en el centro + filamento vertical) ----
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.0022, 0.003, 40),
      new THREE.MeshBasicMaterial({ color: COLORS.source, side: THREE.DoubleSide }));
    const filament = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, -H / 2), new THREE.Vector3(0, 0, H / 2)]),
      new THREE.LineBasicMaterial({ color: COLORS.source }));
    frame.add(ring, filament);

    // ---- Vectores de campo (se pueden ocultar) ----
    this.fieldGroup = new THREE.Group();
    const L = 0.2 * R;
    const zBase = Hc / 2 + (bSign > 0 ? 0 : L);
    const step = 0.4 * R;
    for (let i = -2; i <= 2; i++) {
      for (let j = -2; j <= 2; j++) {
        const x = i * step, y = j * step;
        if (Math.hypot(x, y) > 0.9 * R) continue;
        this.fieldGroup.add(new THREE.ArrowHelper(
          new THREE.Vector3(0, 0, Math.sign(bSign) || 1), new THREE.Vector3(x, y, zBase),
          L, COLORS.bField, 0.4 * L, 0.22 * L));
      }
    }
    this.eArrows = [];
    this.eMaxLength = 0.16 * R;
    if (hasElectric) {
      for (let k = 0; k < 5; k++) {
        const y = (-0.75 + 0.375 * k) * R;
        const a = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, y, 0),
          this.eMaxLength, COLORS.eField, 0.4 * this.eMaxLength, 0.25 * this.eMaxLength);
        this.eArrows.push(a);
        this.fieldGroup.add(a);
      }
    }
    this.fieldGroup.visible = this.fieldVectorsVisible;
    frame.add(this.fieldGroup);

    this.frame = frame;
    this.scene.add(frame);
  }

  /**
   * ratio = E_RF(t)/E0 ∈ [−1, 1], tomado de rf_signal_vm del backend.
   * El signo da el sentido (±x); la longitud, la magnitud relativa. Solo ilustra el dato.
   */
  updateElectricField(ratio) {
    for (const a of this.eArrows) {
      if (Math.abs(ratio) < 0.02) { a.visible = false; continue; }
      a.visible = true;
      const dir = ratio > 0 ? 1 : -1;
      const len = Math.max(Math.abs(ratio) * this.eMaxLength, 1e-6);
      a.setDirection(new THREE.Vector3(dir, 0, 0));
      a.setLength(len, 0.4 * len, 0.25 * len);
      a.position.x = -dir * len / 2;      // centrada en el hueco
    }
  }

  setFieldVectorsVisible(on) {
    this.fieldVectorsVisible = on;
    if (this.fieldGroup) this.fieldGroup.visible = on;
  }

  setChamberOpacity(a) {
    this.opacity.chamber = a;
    for (const m of this.chamberMats) m.opacity = a;
  }

  setDeeOpacity(a) {
    this.opacity.dees = a;
    for (const m of this.deeMats) m.opacity = a;
  }

  dispose() {
    if (!this.frame) return;
    this.scene.remove(this.frame);
    this.frame.traverse((o) => {
      o.geometry?.dispose();
      if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
      else o.material?.dispose();
    });
    this.frame = null;
  }
}