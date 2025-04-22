#include <cstdlib>
#include <filesystem>
#include <sstream>

#include "lib/nullstream.h"
#include "options.h"
#include "p4lacpp.h"

using namespace P4;
using namespace P4LACPP;
int main(int argc, char *const argv[]) {
    AutoCompileContext autoP4LACPPContext(new P4LACPPContext);
    auto &options = P4LACPPContext::get().options();
    if (options.process(argc, argv) == nullptr) {
        return EXIT_FAILURE;
    }
    options.setInputFile();

    // parse with frontend
    auto parseResult = parseProgram(options);
    if (!parseResult) {
        if (::P4::errorCount() > 0) {
            ::P4::error("Failed to parse P4 file.");
        }
        return {};
    }
    const auto &[program, _] = *parseResult;


    dumpAfterFrontend(options, program);
    // TODO: add options for either get feature or annotate
    getFeatures(options, program);

}
