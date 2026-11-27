#include "../sub/firmware/coral_display/rms_direction.h"
#include <cassert>
int main() {
  const float gains[4]={1,1,1,1};
  RmsWindow window;
  for(unsigned i=0;i<512;++i) {
    int sign=i%2 ? 1 : -1;
    uint16_t values[4]={uint16_t(400+sign*10),uint16_t(500+sign*40),uint16_t(600+sign*20),uint16_t(700+sign*5)};
    window.add(values);
  }
  float rms[4],mean[4];window.finish(rms,mean,gains);
  assert(std::abs(rms[1]-40)<.01);assert(std::abs(mean[3]-700)<.01);
  assert(strongestDirection(rms,mean,3,1.1)==1);
  rms[2]=39;assert(strongestDirection(rms,mean,3,1.1)==-1);
  rms[2]=20;mean[0]=0;assert(strongestDirection(rms,mean,3,1.1)==-1);
  RmsWindow quiet;
  for(int i=0;i<100;++i) { uint16_t v[4]={400,500,600,700};quiet.add(v); }
  quiet.finish(rms,mean,gains);
  assert(strongestDirection(rms,mean,3,1.1)==-1);
}
