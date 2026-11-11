#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

constexpr int BLUE_TOP = 0, BLUE_HEIGHT = 48;
constexpr int YELLOW_TOP = 48, YELLOW_HEIGHT = 16;

struct TextPage {
  char lines[8][22] = {};
  uint8_t count = 0;
  size_t next = 0;
};

inline TextPage layoutPage(const char *value, size_t start, int scale, int height = BLUE_HEIGHT) {
  TextPage page;
  const size_t length = strlen(value), columns = 128 / (6 * scale);
  const int rows = height / (8 * scale);
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

inline int textScale(const char *value, int height = BLUE_HEIGHT) {
  for (int scale = 3; scale > 1; --scale) {
    if (8 * scale <= height && !layoutPage(value, 0, scale, height).next) return scale;
  }
  return 1;
}

inline int centeredX(const char *line, int scale) {
  return (128 - int(strlen(line)) * 6 * scale) / 2;
}

inline int centeredY(int line, int count, int scale, int height = BLUE_HEIGHT, int top = BLUE_TOP) {
  return top + (height - count * 8 * scale) / 2 + line * 8 * scale;
}

struct RegionCursor {
  size_t start = 0, next = 0;
  uint8_t index = 0;

  bool advance(uint8_t messages) {
    if (!start && !next && messages <= 1) return false;
    if (next) start = next;
    else { start = 0; index = (index + 1) % messages; }
    return true;
  }
};
