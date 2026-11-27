#include <cassert>
#include "../sub/firmware/coral_display/button.h"
int main() {
 DebouncedButton b; b.begin(false,0);
 assert(!b.update(true,10)); assert(!b.update(false,20));
 assert(!b.update(true,25)); assert(!b.update(true,64)); assert(b.update(true,65));
 assert(!b.update(true,5000)); assert(!b.update(false,5010)); assert(!b.update(false,5050));
 assert(!b.update(true,5060)); assert(b.update(true,5100));
 b.begin(true,0); assert(!b.update(true,1000));
 b.begin(false,0xfffffff0); assert(!b.update(true,0xfffffff5)); assert(b.update(true,35));
}
