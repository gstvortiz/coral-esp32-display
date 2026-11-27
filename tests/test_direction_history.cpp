#include "../sub/firmware/coral_display/direction_history.h"
#include <cassert>
#include <cmath>

int main() {
  DirectionHistory history;
  const float mean[4]={512,512,512,512};
  const float south[4]={5,5,50,5},north[4]={50,5,5,5};
  // Bird sang in the south during [1s,4s]; a new source is now north.
  for(uint64_t t=1000000;t<4000000;t+=100000) history.add(t,t+100000,south,mean);
  for(uint64_t t=4000000;t<7000000;t+=100000) history.add(t,t+100000,north,mean);
  auto old=history.select(1000000,4000000,3,1.1);
  assert(old.direction==2 && std::abs(old.coverage-1)<.001);
  assert(history.select(4000000,7000000,3,1.1).direction==0);
  assert(history.select(2500000,5500000,3,1.1).direction==-1); // Equal energy.
  assert(history.select(0,3000000,3,1.1).direction==-1); // Missing boot history.
  assert(history.select(6500000,9500000,3,1.1).direction==-1); // Future/incomplete.
  assert(history.select(4000000,4000000,3,1.1).direction==-1);
  // Boundary overlap uses time weights, not a count of frames or live winner.
  DirectionHistory boundary;
  boundary.add(1000000,2000000,south,mean);
  boundary.add(2000000,3000000,north,mean);
  assert(boundary.select(1900000,3000000,3,1.1).direction==0);
  // Overwritten history must not be mistaken for current samples.
  for(uint64_t t=7000000;t<30000000;t+=100000) history.add(t,t+100000,north,mean);
  assert(history.select(1000000,4000000,3,1.1).direction==-1);
  assert(history.select(27000000,30000000,3,1.1).direction==0);
  assert(old.direction==2); // Saved observation is independent of later samples.
  DirectionHistory invalid;
  const float badMean[4]={0,512,512,512};
  invalid.add(100,200,south,badMean);
  assert(invalid.select(100,200,3,1.1).direction==-1);
  uint64_t start=0,end=0;
  assert(mapAudioWindow(7000000,100000,94500,97500,start,end));
  assert(start==1500000 && end==4500000);
  // Advancing both clocks on a retry maps to the same historical interval.
  assert(mapAudioWindow(8000000,101000,94500,97500,start,end));
  assert(start==1500000 && end==4500000);
  assert(!mapAudioWindow(2000000,100000,94500,97500,start,end));
  assert(!mapAudioWindow(7000000,100000,99000,100001,start,end));
  assert(!mapAudioWindow(7000000,100000,0,0,start,end));
}
