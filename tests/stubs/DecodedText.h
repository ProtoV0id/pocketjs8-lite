#pragma once
#include <string>
class DecodedText {
public: DecodedText(const std::string&,int,int); std::string message() const;bool isLowConfidence() const;
};
