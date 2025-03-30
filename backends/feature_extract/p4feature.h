#ifndef BACKENDS_P4FEATURE_H_
#define BACKENDS_P4FEATURE_H_

#include "ir/ir.h"
#include "ir/visitor.h"
#include "options.h"

namespace P4::P4Features{
std::string getFeatures(std::filesystem::path inputFile);

} // namespace P4::P4Features


#endif /* BACKENDS_P4FEATURE_H_ */