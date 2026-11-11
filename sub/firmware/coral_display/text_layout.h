#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

struct TextPage {
  char lines[8][22] = {};
  uint8_t count = 0;
  size_t next = 0;
};

inline TextPage layoutPage(const char *value, size_t start, int scale) {
  TextPage page;
  const size_t length = strlen(value), columns = 128 / (6 * scale);
  const int rows = 64 / (8 * scale);
  size_t pos = start;
  while (pos < length && page.count < rows) {
    size_t end = pos;
    while (end < length && end - pos < columns && value[end] != '\n') ++end;
    if (end < length && value[end] != '\n' && value[end] != ' ') {
      size_t space = end;
      while (space > pos && value[space - 1] != ' ') --space;
      if (space > pos) end = space - 1;
      if (end == pos) end = pos + columns;
    }
    size_t visible = end - pos;
    while (visible && value[pos + visible - 1] == ' ') --visible;
    memcpy(page.lines[page.count++], value + pos, visible);
    pos = end;
    if (pos < length && value[pos] == '\n') ++pos;
    else while (pos < length && value[pos] == ' ') ++pos;
  }
  if (!page.count) page.count = 1;
  page.next = pos < length ? pos : 0;
  return page;
}

inline int textScale(const char *value) {
  for (int scale = 3; scale > 1; --scale) {
    if (!layoutPage(value, 0, scale).next) return scale;
  }
  return 1;
}

inline int centeredX(const char *line, int scale) {
  return (128 - int(strlen(line)) * 6 * scale) / 2;
}

inline int centeredY(int line, int count, int scale) {
  return (64 - count * 8 * scale) / 2 + line * 8 * scale;
}
