#include "options.h"

namespace P4::P4Features {

P4FeaturesOptions::P4FeaturesOptions() {
    registerOption(
        "-o", "outfile",
        [this](const char *arg) {
            outFile = arg;
            return true;
        },
        "Write features to outfile");
}

const std::filesystem::path &P4FeaturesOptions::outputFile() const { return outFile; }

}  // namespace P4::P4Fmt
