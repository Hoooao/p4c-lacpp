#include <cstdlib>
#include <filesystem>
#include <sstream>

#include "lib/nullstream.h"
#include "options.h"
#include "p4lacpp.h"

using namespace P4;

int main(int argc, char *const argv[]) {
    AutoCompileContext autoP4LACPPContext(new P4LACPP::P4LACPPContext);
    auto &options = P4LACPP::P4LACPPContext::get().options();
    if (options.process(argc, argv) == nullptr) {
        return EXIT_FAILURE;
    }
    options.setInputFile();

    // TODO: add options for either get feature or annotate
    std::string featuresInJson = P4LACPP::getFeatures(options.file);
    if (featuresInJson.empty()) {
        return EXIT_FAILURE;
    };

    std::ostream *out = nullptr;
    // Write to stdout in absence of an output file.
    if (options.outputFile().empty()) {
        out = &std::cout;
    } else {
        out = openFile(options.outputFile(), false);
        if ((out == nullptr) || !(*out)) {
            ::P4::error(ErrorType::ERR_NOT_FOUND, "%2%: No such file or directory.",
                        options.outputFile().string());
            options.usage();
            return EXIT_FAILURE;
        }
    }

    (*out) << featuresInJson;
    out->flush();
    if (!(*out)) {
        ::P4::error(ErrorType::ERR_IO, "Failed to write to output file.");
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
