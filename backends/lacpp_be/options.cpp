#include "options.h"

namespace P4::P4LACPP {

P4LACPPOptions::P4LACPPOptions() {
    registerOption(
        "-f", "feature-file",
        [this](const char *arg) {
            featureOutFile = arg;
            return true;
        },
        "Write features to outfile");
    registerOption(
        "--post-midend-source", "file",
        [this](const char *arg) {
            dumpOptimizedFile = arg;
            return true;
        },
        "Get the source code after midend and write it to the specified file then end the program");
    registerOption(
        "--rewrite", nullptr,
        [this](const char *) {
            rewrite_mode = true;
            return true;
        },
        "Start sampler");

}

const std::filesystem::path &P4LACPPOptions::getFeatureOutFile() const { return featureOutFile; }
const std::filesystem::path &P4LACPPOptions::getDumpOptimizedFile() const { return dumpOptimizedFile; }
bool P4LACPPOptions::getRewriteMode() const { return rewrite_mode; }

}  // namespace P4::P4Fmt
