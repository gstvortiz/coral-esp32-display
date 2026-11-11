#include "../sub/firmware/coral_display/text_layout.h"
#include <assert.h>
#include <string>

int main() {
  assert(textScale("Coral") == 3);
  auto shortPage = layoutPage("Coral", 0, 3);
  assert(shortPage.count == 1 && shortPage.next == 0);
  assert(centeredX(shortPage.lines[0], 3) == 19);
  assert(centeredY(0, 1, 3) == 20);
  auto multi = layoutPage("linha\noutra", 0, 3);
  assert(multi.count == 2);
  assert(centeredY(0, 2, 3) == 8 && centeredY(1, 2, 3) == 32);
  auto words = layoutPage("Ola mundo", 0, 3);
  assert(!strcmp(words.lines[0], "Ola") && !strcmp(words.lines[1], "mundo"));
  for (auto message : {std::string(1024, 'a'), std::string(1024, '\n'),
                       std::string(1024, ' '), std::string(""),
                       std::string("um dois tres quatro cinco seis sete oito nove dez")}) {
    int scale = textScale(message.c_str());
    size_t start = 0;
    int pages = 0;
    do {
      auto page = layoutPage(message.c_str(), start, scale);
      assert(page.count >= 1 && page.count <= 8);
      for (int line = 0; line < page.count; ++line) {
        assert(strlen(page.lines[line]) <= size_t(128 / (6 * scale)));
        int x = centeredX(page.lines[line], scale), y = centeredY(line, page.count, scale);
        assert(x >= 0 && y >= 0 && y + 8 * scale <= 64);
      }
      assert(page.next == 0 || page.next > start);
      start = page.next;
      assert(++pages <= 1024);
    } while (start);
  }
}
