#ifndef BACKENDS_P4LACPP_OPTIONS_H_
#define BACKENDS_P4LACPP_OPTIONS_H_

#include "frontends/common/options.h"
#include "frontends/common/parser_options.h"

namespace P4::P4LACPP {

class P4LACPPOptions : public CompilerOptions {
 public:
    P4LACPPOptions();
    virtual ~P4LACPPOptions() = default;
    P4LACPPOptions(const P4LACPPOptions &) = default;
    P4LACPPOptions(P4LACPPOptions &&) = delete;
    P4LACPPOptions &operator=(const P4LACPPOptions &) = default;
    P4LACPPOptions &operator=(P4LACPPOptions &&) = delete;

    const std::filesystem::path &outputFile() const;

 private:
    std::filesystem::path outFile;
};

using P4LACPPContext = P4CContextWithOptions<P4LACPPOptions>;

}  // namespace P4::P4LACPP

#endif /* BACKENDS_P4LACPP_OPTIONS_H_ */
