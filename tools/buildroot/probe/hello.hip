#include <hip/hip_runtime.h>
#include <cstdio>
__global__ void vadd(const float* a, const float* b, float* c, int n) {
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < n) c[i] = a[i] + b[i];
}
#define CK(x) do { hipError_t e = (x); if (e != hipSuccess) { std::printf("HIP error %s at %s\n", hipGetErrorString(e), #x); return 1; } } while (0)
int main() {
  int rt = 0, drv = 0; CK(hipRuntimeGetVersion(&rt)); CK(hipDriverGetVersion(&drv));
  hipDeviceProp_t p; CK(hipGetDeviceProperties(&p, 0));
  std::printf("compiled HIP_VERSION=%d runtime=%d driver=%d device=%s arch=%s\n", HIP_VERSION, rt, drv, p.name, p.gcnArchName);
  const int n = 1 << 20; size_t bytes = n * sizeof(float);
  float *a, *b, *c; CK(hipMallocManaged(&a, bytes)); CK(hipMallocManaged(&b, bytes)); CK(hipMallocManaged(&c, bytes));
  for (int i = 0; i < n; ++i) { a[i] = i; b[i] = 2.0f * i; }
  vadd<<<(n + 255) / 256, 256>>>(a, b, c, n); CK(hipGetLastError()); CK(hipDeviceSynchronize());
  for (int i = 0; i < n; ++i) if (c[i] != 3.0f * i) { std::printf("mismatch at %d\n", i); return 2; }
  std::printf("vadd OK n=%d\n", n); return 0;
}
