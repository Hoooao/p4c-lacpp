#ifndef BACKENDS_P4LACPP_H_
#define BACKENDS_P4LACPP_H_

#include "ir/ir.h"
#include "ir/visitor.h"
#include "options.h"

namespace P4::P4LACPP{
std::optional<std::pair<const IR::P4Program *, const Util::InputSources *>> parseProgram(
    const ParserOptions &options);
    
int getFeatures(P4LACPPOptions& options, const IR::P4Program *program);
int dumpAfterFrontend(P4LACPPOptions& options, const IR::P4Program *program);
} // namespace P4::P4LACPP


#endif /* BACKENDS_P4LACPP_H_ */