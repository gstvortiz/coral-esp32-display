#pragma once
#include <stdint.h>
// Active-low, one event after 40 ms stable press; a held button never repeats.
class DebouncedButton {
  bool stable=false,raw=false;
  uint32_t changed=0;
public:
  void begin(bool pressed,uint32_t now) {stable=raw=pressed;changed=now;}
  bool update(bool pressed,uint32_t now) {
    if(pressed!=raw) {raw=pressed;changed=now;}
    if(raw!=stable && uint32_t(now-changed)>=40) {stable=raw;return stable;}
    return false;
  }
};
