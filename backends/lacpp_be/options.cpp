#include "options.h"

namespace P4::P4LACPP {

P4LACPPOptions::P4LACPPOptions() {
    registerOption(
        "-o", "outfile",
        [this](const char *arg) {
            outFile = arg;
            return true;
        },
        "Write features to outfile");
}

const std::filesystem::path &P4LACPPOptions::outputFile() const { return outFile; }

}  // namespace P4::P4Fmt
