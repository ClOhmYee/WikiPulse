import { Matrix4, Raycaster } from "three";

// Reuse scratch objects: one ray per frame, one intersection per node.
export function createFieldPointer() {
  const raycaster = new Raycaster();
  const inverseWorld = new Matrix4();

  return {
    update(pointer, camera, matrixWorld) {
      raycaster.setFromCamera(pointer, camera);
      inverseWorld.copy(matrixWorld).invert();
      raycaster.ray.applyMatrix4(inverseWorld);
    },
    atDepth(depth, target) {
      const { ray } = raycaster;
      if (Math.abs(ray.direction.z) < 1e-8) return false;
      const distance = (depth - ray.origin.z) / ray.direction.z;
      if (distance < 0) return false;
      ray.at(distance, target);
      return true;
    },
  };
}
