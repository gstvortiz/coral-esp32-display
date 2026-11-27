#pragma once
#include <cmath>
#include <cstdint>
struct RmsWindow {
  uint64_t sum[4]={}, squares[4]={};
  unsigned count=0;
  void add(const uint16_t values[4]) {
    for(int i=0;i<4;++i) { sum[i]+=values[i]; squares[i]+=uint32_t(values[i])*values[i]; }
    ++count;
  }
  void finish(float rms[4], float mean[4], const float gains[4]) const {
    for(int i=0;i<4;++i) {
      mean[i]=count ? double(sum[i])/count : 0;
      const double variance=count ? double(squares[i])/count-std::pow(double(sum[i])/count,2) : 0;
      rms[i]=std::sqrt(variance>0 ? variance : 0)*gains[i];
    }
  }
};
inline int strongestDirection(const float rms[4],const float mean[4],float floor,float ratio) {
  int winner=0; float second=0;
  for(int i=0;i<4;++i) {
    // Disconnected/stuck ADC inputs must not produce a claimed direction.
    if(mean[i]<5 || mean[i]>1018 || !std::isfinite(rms[i])) return -1;
    if(rms[i]>rms[winner]) winner=i;
  }
  for(int i=0;i<4;++i) if(i!=winner && rms[i]>second) second=rms[i];
  return rms[winner]>=floor && rms[winner]>second*ratio ? winner : -1;
}
