import * as THREE from "three";
import { physicalToScene } from "./scene.js";

// Tamaños SOLO visuales, proporcionales al radio de la escena. No representan tamaños físicos.
const PARTICLE_VISUAL_FRACTION = 0.022;   // radio de la esfera = 2.2 % del radio de los dees
const ARROW_VISUAL_FRACTION = 0.14;       // longitud de la flecha = 14 % del radio de los dees

export class ParticleView {
  constructor(scene) {
    this.group = new THREE.Group();
    // Esfera unitaria; el tamaño visual se fija con group.scale (setVisualSize)
    this.group.add(new THREE.Mesh(
      new THREE.SphereGeometry(1, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0x4cc9ff }),
    ));
    this.group.add(new THREE.Mesh(      // halo translúcido
      new THREE.SphereGeometry(2.4, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0x4cc9ff, transparent: true, opacity: 0.22, depthWrite: false }),
    ));
    this.arrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 1, 0x9dff6a);
    this.arrowEnabled = true;
    scene.add(this.group, this.arrow);
    this.setVisualSize(5);
  }

  /** sceneRadius = radio de los dees en unidades de escena. */
  setVisualSize(sceneRadius) {
    this.group.scale.setScalar(PARTICLE_VISUAL_FRACTION * sceneRadius);
    const len = ARROW_VISUAL_FRACTION * sceneRadius;
    this.arrow.setLength(len, len * 0.35, len * 0.2);
  }

  /** position y velocity son arreglos [x,y,z] en SI, tal como los devolvió el backend. */
  setSample(position, velocity) {
    const p = physicalToScene(position);
    this.group.position.copy(p);
    this.arrow.position.copy(p);
    const dir = physicalToScene(velocity);     // solo importa la dirección
    if (dir.lengthSq() > 0) {
      this.arrow.setDirection(dir.normalize());
      this.arrow.visible = this.arrowEnabled;
    } else {
      this.arrow.visible = false;               // v = 0: no hay dirección
    }
  }

  setArrowVisible(on) {
    this.arrowEnabled = on;
    if (!on) this.arrow.visible = false;
  }
}

/** Línea formada por los puntos que calculó el backend, sin suavizado ni interpolación. */
export class TrajectoryLine {
  constructor(scene, capacity) {
    this.capacity = capacity;
    this.count = 0;
    this.positions = new Float32Array(capacity * 3);
    this.geometry = new THREE.BufferGeometry();
    this.attribute = new THREE.BufferAttribute(this.positions, 3);
    this.geometry.setAttribute("position", this.attribute);
    this.geometry.setDrawRange(0, 0);
    this.line = new THREE.Line(this.geometry, new THREE.LineBasicMaterial({ color: 0xffb703 }));
    this.line.frustumCulled = false;
    scene.add(this.line);
  }

  addPoints(points) {
    for (const p of points) {
      if (this.count >= this.capacity) break;
      const v = physicalToScene(p);
      this.positions[this.count * 3] = v.x;
      this.positions[this.count * 3 + 1] = v.y;
      this.positions[this.count * 3 + 2] = v.z;
      this.count++;
    }
    this.attribute.needsUpdate = true;
  }

  /** Muestra solo los primeros n puntos (los ya "alcanzados" por la reproducción). */
  setVisibleCount(n) {
    this.geometry.setDrawRange(0, Math.min(n, this.count));
  }

  clear() {
    this.count = 0;
    this.geometry.setDrawRange(0, 0);
  }

  setVisible(on) {
    this.line.visible = on;
  }
}