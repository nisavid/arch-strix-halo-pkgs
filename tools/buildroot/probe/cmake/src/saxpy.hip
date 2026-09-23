#include <hip/hip_runtime.h>
__global__ void k(float a, const float* x, float* y, int n) { int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) y[i] = a * x[i] + y[i]; }
extern "C" int saxpy(float a, const float* x, float* y, int n) {
  float *dx, *dy; size_t b = n * sizeof(float);
  if (hipMalloc(&dx, b) || hipMalloc(&dy, b)) return -1;
  hipMemcpy(dx, x, b, hipMemcpyHostToDevice); hipMemcpy(dy, y, b, hipMemcpyHostToDevice);
  k<<<(n + 127) / 128, 128>>>(a, dx, dy, n);
  hipMemcpy(y, dy, b, hipMemcpyDeviceToHost); hipFree(dx); hipFree(dy);
  return hipDeviceSynchronize() == hipSuccess ? 0 : -2;
}
extern "C" int saxpy_runtime_version() { int v = 0; hipRuntimeGetVersion(&v); return v; }
