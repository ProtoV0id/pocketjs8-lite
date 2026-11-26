#include "gfsk8modem.h"
#include "DecodedText.h"
#include <string>
#include <vector>
namespace gfsk8 {
std::vector<TxFrame> pack(const std::string &,const std::string &,const std::string &text,Submode) {
    if(text.empty())return {};
    return std::vector<TxFrame>((text.size()+12)/13,{"TESTTEST1234",0});
}
std::vector<float> modulate(Submode,int,std::string_view,double) {
    return std::vector<float>(150000,0.2f);
}
Decoder::Decoder(int,int,int) {}
void Decoder::decode(std::span<const std::int16_t>,int,const std::function<void(const Decoded&)>& callback) {
    callback(Decoded{"TESTTEST1234",-12,1500.0f,0.2f,0,0.9f,0,0});
}
}
DecodedText::DecodedText(const std::string&,int,int) {}
std::string DecodedText::message() const {return "MOCK MESSAGE";}
bool DecodedText::isLowConfidence() const {return false;}
