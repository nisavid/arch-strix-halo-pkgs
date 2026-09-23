#include <cstdio>
extern "C" int saxpy(float, const float*, float*, int);
extern "C" int saxpy_runtime_version();
int main() {
  const int n = 4096; static float x[n], y[n];
  for (int i = 0; i < n; ++i) { x[i] = i; y[i] = 1; }
  int rc = saxpy(2.0f, x, y, n);
  for (int i = 0; i < n; ++i) if (y[i] != 2.0f * i + 1) { std::printf("mismatch %d\n", i); return 2; }
  std::printf("saxpy OK rc=%d runtime=%d\n", rc, saxpy_runtime_version()); return rc;
}
