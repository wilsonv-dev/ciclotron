import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// ---------- Conversión metros físicos → unidades de escena (centralizada) ----------
// scale = unidades de escena por metro. 100 → 1 unidad = 1 cm.
// Solo afecta al dibujo: nunca a masa, carga ni velocidad físicas.
export const view = { scale: 100 };

export function metersToScene(m) {
  return m * view.scale;
}

// Físico (x, y, z) con B ∥ z  →  Three.js (x, z, −y): conserva la orientación derecha.
export function physicalToScene(p) {
  return new THREE.Vector3(metersToScene(p[0]), metersToScene(p[2]), -metersToScene(p[1]));
}

/**
 * Grupo cuyo sistema LOCAL es el sistema físico (metros). Todo lo que se añada dentro puede
 * posicionarse con medidas SI. Aplica la misma transformación que physicalToScene:
 * rotación de −90° sobre X (y→z, z→−y) y escala view.scale.
 */
export function makePhysicalFrame() {
  const g = new THREE.Group();
  g.rotation.x = -Math.PI / 2;
  g.scale.setScalar(view.scale);
  g.updateMatrixWorld(true);
  const viaFrame = g.localToWorld(new THREE.Vector3(1, 2, 3));
  const viaFunction = physicalToScene([1, 2, 3]);
  console.assert(viaFrame.distanceTo(viaFunction) < 1e-9,
    "makePhysicalFrame y physicalToScene no coinciden");
  return g;
}

function makeLabel(text, color, sceneRadius) {
  const canvas = document.createElement("canvas");
  canvas.width = 128; canvas.height = 64;
  const g = canvas.getContext("2d");
  g.font = "bold 40px system-ui, sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillStyle = color;
  g.fillText(text, 64, 32);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas), transparent: true, depthTest: false,
  }));
  sprite.scale.set(0.14 * sceneRadius, 0.07 * sceneRadius, 1);
  return sprite;
}

function makeAxis(dirPhysical, lengthM, color, label, sceneRadius) {
  const tip = physicalToScene(dirPhysical.map((c) => c * lengthM));
  const geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), tip]);
  const group = new THREE.Group();
  group.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color })));
  const sprite = makeLabel(label, "#" + color.toString(16).padStart(6, "0"), sceneRadius);
  sprite.position.copy(tip.clone().multiplyScalar(1.08));
  group.add(sprite);
  return group;
}

export function createScene(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070b14);

  const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 500);
  camera.position.set(6, 8, 10);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // ---------- CONTROL MANUAL DE ZOOM (SUAVE Y PROGRESIVO) ----------
  controls.enableZoom = false; // Desactivamos el zoom brusco por defecto de OrbitControls
  const minZoomDist = 0.5;
  const maxZoomDist = 300;

  container.addEventListener("wheel", (event) => {
    event.preventDefault();
    const delta = Math.sign(event.deltaY);
    const distance = camera.position.distanceTo(controls.target);
    const step = distance * 0.1; // Desplazamiento proporcional a la distancia actual
    const newDistance = distance + delta * step;

    if (newDistance >= minZoomDist && newDistance <= maxZoomDist) {
      const dir = camera.position.clone().sub(controls.target).normalize();
      camera.position.copy(controls.target).add(dir.multiplyScalar(newDistance));
    }
  }, { passive: false });
  // ------------------------------------------------------------------

  const axes = new THREE.Group();
  scene.add(axes);
  let grid = null;

  /** Ajusta ejes, rejilla y (opcionalmente) la cámara al tamaño de la geometría física. */
  function fitToGeometry(geometry, resetCamera) {
    const R = geometry.dee_radius_m;
    const Rs = metersToScene(R);

    axes.clear();
    const L = 1.3 * R;
    axes.add(makeAxis([1, 0, 0], L, 0xff5c5c, "X", Rs));
    axes.add(makeAxis([0, 1, 0], L, 0x4cf08a, "Y", Rs));
    axes.add(makeAxis([0, 0, 1], L, 0xc77dff, "Z (B)", Rs));

    if (grid) { scene.remove(grid); grid.geometry.dispose(); grid.material.dispose(); }
    grid = new THREE.GridHelper(Rs * 3, 12, 0x1f6feb, 0x16233a);
    grid.position.y = -metersToScene(geometry.height_m) * 0.8;   // debajo de la cámara de vacío
    scene.add(grid);

    camera.near = Rs * 0.01;
    camera.far = Rs * 60;
    camera.updateProjectionMatrix();
    if (resetCamera) {
      camera.position.set(1.0 * Rs, 1.5 * Rs, 1.9 * Rs);
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (w === 0 || h === 0) return;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  return { scene, camera, renderer, controls, axes, fitToGeometry,
           render: () => renderer.render(scene, camera) };
}