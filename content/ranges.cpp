#include <algorithm>
#include <print>
#include <vector>

int main() {
  std::vector values{4, 2, 3, 1};
  std::ranges::sort(values);

  for (int value : values) {
    std::println("value: {}", value);
  }
}
