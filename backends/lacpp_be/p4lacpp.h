#ifndef BACKENDS_P4LACPP_H_
#define BACKENDS_P4LACPP_H_

#include "ir/ir.h"
#include "ir/visitor.h"
#include "options.h"

namespace P4::P4LACPP{
std::string getFeatures(std::filesystem::path inputFile);

} // namespace P4::P4LACPP


#endif /* BACKENDS_P4LACPP_H_ */