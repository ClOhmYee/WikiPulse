import assert from "node:assert/strict";
import test from "node:test";
import { Object3D, PerspectiveCamera, Vector2, Vector3 } from "three";
import { createFieldPointer } from "../src/pages/onboarding/fieldPointer.js";

test("pointer stays under the cursor across resize, depth and field transforms", () => {
  const camera = new PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 5.9);
  camera.updateMatrixWorld();
  const field = new Object3D();
  const pointer = createFieldPointer();
  const hit = new Vector3();

  for (const [width, height] of [[1440, 1000], [1920, 1080], [390, 844]]) {
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    for (const scale of [0.46, 0.54, 1]) {
      for (const rotation of [0, 0.35]) {
        field.scale.setScalar(scale);
        field.rotation.set(-rotation * 0.5, rotation, rotation * 0.1);
        field.position.set(rotation ? 1.7 : 0, rotation ? 0.07 : 0, 0);
        field.updateMatrixWorld();
        for (const x of [-0.8, 0, 0.8]) {
          for (const y of [-0.7, 0, 0.7]) {
            const cursor = new Vector2(x, y);
            pointer.update(cursor, camera, field.matrixWorld);
            for (const depth of [-1.2, 0, 1.2]) {
              assert.equal(pointer.atDepth(depth, hit), true);
              const screen = hit.clone().applyMatrix4(field.matrixWorld).project(camera);
              const error = Math.hypot((screen.x - x) * width / 2, (screen.y - y) * height / 2);
              assert.ok(error < 0.001, `cursor error ${error}px at ${width}x${height}, scale ${scale}`);
            }
          }
        }
      }
    }
  }
});

test("a node projected to the cursor has zero local interaction distance", () => {
  const camera = new PerspectiveCamera(42, 16 / 9, 0.1, 100);
  camera.position.z = 5.9;
  camera.updateMatrixWorld();
  const field = new Object3D();
  field.scale.setScalar(0.54);
  field.updateMatrixWorld();
  const pointer = createFieldPointer();
  const hit = new Vector3();
  for (const x of [-4, 0, 4]) {
    const node = new Vector3(x, 0.6, -0.5);
    const screen = node.clone().applyMatrix4(field.matrixWorld).project(camera);
    pointer.update(screen, camera, field.matrixWorld);
    assert.equal(pointer.atDepth(node.z, hit), true);
    assert.ok(hit.distanceTo(node) < 1e-10);
  }
});

test("parallel and behind-camera planes have no pointer hit", () => {
  const camera = new PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.z = 5.9;
  camera.updateMatrixWorld();
  const field = new Object3D();
  const pointer = createFieldPointer();
  const hit = new Vector3();
  pointer.update(new Vector2(), camera, field.matrixWorld);
  assert.equal(pointer.atDepth(6, hit), false);
  field.rotation.y = Math.PI / 2;
  field.updateMatrixWorld();
  pointer.update(new Vector2(), camera, field.matrixWorld);
  assert.equal(pointer.atDepth(0, hit), false);
});
