#include "../sub/firmware/coral_display/text_layout.h"
#include <assert.h>
#include <string>

int main() {
  assert(textScale("Coral") == 3);
  auto shortPage = layoutPage("Coral", 0, 3);
  assert(shortPage.count == 1 && shortPage.next == 0);
  assert(centeredX(shortPage.lines[0], 3) == 19);
  assert(centeredY(0, 1, 3) == 12);
  assert(textScale("Pronta", YELLOW_HEIGHT) == 2);
  assert(centeredY(0, 1, 2, YELLOW_HEIGHT, YELLOW_TOP) == 48);
  auto multi = layoutPage("linha\noutra", 0, 3);
  assert(multi.count == 2);
  assert(centeredY(0, 2, 3) == 0 && centeredY(1, 2, 3) == 24);
  auto words = layoutPage("Ola mundo", 0, 3);
  assert(!strcmp(words.lines[0], "Ola") && !strcmp(words.lines[1], "mundo"));
  for (int height : {BLUE_HEIGHT, YELLOW_HEIGHT}) {
  int top = height == BLUE_HEIGHT ? BLUE_TOP : YELLOW_TOP;
  for (auto message : {std::string(1024, 'a'), std::string(1024, '\n'),
                       std::string(1024, ' '), std::string(""),
                       std::string("um dois tres quatro cinco seis sete oito nove dez")}) {
    int scale = textScale(message.c_str(), height);
    size_t start = 0;
    int pages = 0;
    do {
      auto page = layoutPage(message.c_str(), start, scale, height);
      assert(page.count >= 1 && page.count <= height / (8 * scale));
      for (int line = 0; line < page.count; ++line) {
        assert(strlen(page.lines[line]) <= size_t(128 / (6 * scale)));
        int x = centeredX(page.lines[line], scale), y = centeredY(line, page.count, scale, height, top);
        assert(x >= 0 && y >= top && y + 8 * scale <= top + height);
      }
      assert(page.next == 0 || page.next > start);
      start = page.next;
      assert(++pages <= 1024);
    } while (start);
  }
  }
  RegionCursor fixed, rotating;
  assert(!fixed.advance(1));
  rotating.next = 42;
  assert(rotating.advance(2) && rotating.start == 42 && rotating.index == 0);
  rotating.next = 0;
  assert(rotating.advance(2) && rotating.start == 0 && rotating.index == 1);
  assert(rotating.advance(2) && rotating.index == 0);
  assert(fixed.start == 0 && fixed.index == 0 && !fixed.advance(1));
  rotating.start = 42;
  assert(rotating.advance(1) && rotating.start == 0 && rotating.index == 0);
}
