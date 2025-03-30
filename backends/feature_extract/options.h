#ifndef BACKENDS_P4FMT_OPTIONS_H_
#define BACKENDS_P4FMT_OPTIONS_H_

#include "frontends/common/options.h"
#include "frontends/common/parser_options.h"

namespace P4::P4Features {

class P4FeaturesOptions : public CompilerOptions {
 public:
    P4FeaturesOptions();
    virtual ~P4FeaturesOptions() = default;
    P4FeaturesOptions(const P4FeaturesOptions &) = default;
    P4FeaturesOptions(P4FeaturesOptions &&) = delete;
    P4FeaturesOptions &operator=(const P4FeaturesOptions &) = default;
    P4FeaturesOptions &operator=(P4FeaturesOptions &&) = delete;

    const std::filesystem::path &outputFile() const;

 private:
    std::filesystem::path outFile;
};

using P4FeaturesContext = P4CContextWithOptions<P4FeaturesOptions>;

}  // namespace P4::P4Fmt

#endif /* BACKENDS_P4FMT_OPTIONS_H_ */
