#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include <functional>
#include <span>
namespace gfsk8 {
enum class Submode:int {Normal=0};
struct TxFrame {std::string payload;int frameType;};
struct Decoded {std::string message; int snrDb; float frequencyHz,dtSeconds;int submode;float quality;int frameType,utc;};
std::vector<TxFrame> pack(const std::string&,const std::string&,const std::string&,Submode);
std::vector<float> modulate(Submode,int,std::string_view,double);
class Decoder {
 public:Decoder(int,int,int);void decode(std::span<const std::int16_t>,int,const std::function<void(const Decoded&)>&);
};
}
