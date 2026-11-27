#pragma once
#include "rms_direction.h"
#include <cstddef>

// A bounded history in ESP monotonic time. No wall-clock jumps affect acquisition.
struct DirectionWindow {
  float rms[4]={}, mean[4]={}, coverage=0;
  int direction=-1;
};

class DirectionHistory {
  struct Frame {
    uint64_t start=0,end=0;
    float rms[4]={},mean[4]={};
  };
  static constexpr unsigned CAPACITY=160; // About 23 seconds at 144 ms/frame.
  Frame frames[CAPACITY];
  unsigned next=0,count=0;
public:
  void add(uint64_t start,uint64_t end,const float rms[4],const float mean[4]) {
    if(end<=start) return;
    Frame &frame=frames[next];frame.start=start;frame.end=end;
    for(int ch=0;ch<4;++ch) {frame.rms[ch]=rms[ch];frame.mean[ch]=mean[ch];}
    next=(next+1)%CAPACITY;if(count<CAPACITY) ++count;
  }
  DirectionWindow select(uint64_t start,uint64_t end,float floor,float ratio) const {
    DirectionWindow result;
    if(end<=start) return result;
    double energy[4]={},means[4]={},covered=0;
    bool valid=true;
    for(unsigned i=0;i<count;++i) {
      const Frame &f=frames[i];
      uint64_t lo=f.start>start ? f.start : start;
      uint64_t hi=f.end<end ? f.end : end;
      if(hi<=lo) continue;
      const double weight=hi-lo;covered+=weight;
      for(int ch=0;ch<4;++ch) {
        if(!std::isfinite(f.rms[ch]) || !std::isfinite(f.mean[ch]) ||
           f.mean[ch]<5 || f.mean[ch]>1018) valid=false;
        energy[ch]+=double(f.rms[ch])*f.rms[ch]*weight;
        means[ch]+=f.mean[ch]*weight;
      }
    }
    result.coverage=covered/double(end-start);
    if(!covered) return result;
    for(int ch=0;ch<4;++ch) {
      result.rms[ch]=std::sqrt(energy[ch]/covered);
      result.mean[ch]=means[ch]/covered;
    }
    // Missing history (boot, overwritten frames, capture gaps) is never replaced
    // by the current direction. Small scheduling gaps between frames are allowed.
    if(valid && result.coverage>=0.95f)
      result.direction=strongestDirection(result.rms,result.mean,floor,ratio);
    return result;
  }
};

// Translate Coral epoch timestamps using the clock sample sent with this command.
// The serial transport delay is a small residual uncertainty, not model latency.
inline bool mapAudioWindow(uint64_t nowUs,uint64_t epochMs,uint64_t startMs,
                           uint64_t endMs,uint64_t &startUs,uint64_t &endUs) {
  if(!startMs || endMs<=startMs || endMs>epochMs || endMs-startMs>10000) return false;
  uint64_t ageMs=epochMs-startMs;
  if(ageMs>nowUs/1000) return false; // Window starts before this ESP boot.
  startUs=nowUs-ageMs*1000;
  endUs=nowUs-(epochMs-endMs)*1000;
  return true;
}
