#include "frontends/common/options.h"
#include "frontends/common/parseInput.h"
#include "frontends/common/parser_options.h"
#include "frontends/parsers/parserDriver.h"
#include "frontends/p4/frontend.h"
#include "frontends/p4/toP4/toP4.h"
#include "ir/ir.h"
#include "lib/nullstream.h"

#include "backends/lacpp_be/p4lacpp.h"
#include "backends/lacpp_be/p4feature_extractor.h"


namespace P4::P4LACPP{

// Hao: add this so that we can get the optimized code but maintain the original semantics
class DumpOptimized : public Inspector {
    /// output file
    std::filesystem::path ppfile;
    /// The file that is being compiled.
    std::filesystem::path inputfile;

 public:
    explicit DumpOptimized(const P4LACPPOptions &options) {
        setName("DumpOptimized");
        ppfile = options.getDumpOptimizedFile();
        inputfile = options.file;
    }
    bool preorder(const IR::P4Program *program) override {
        if (!ppfile.empty()) {
            std::ostream *ppStream = openFile(ppfile, true);
            P4::ToP4 top4(ppStream, false, inputfile);
            (void)program->apply(top4);
        }
        return false;  // prune
    }
};


std::optional<std::pair<const IR::P4Program *, const Util::InputSources *>> parseProgram(
    const ParserOptions &options) {
    if (!std::filesystem::exists(options.file)) {
        ::P4::error(ErrorType::ERR_NOT_FOUND, "%1%: No such file found.", options.file);
        return std::nullopt;
    }
    auto preprocessorResult = options.preprocess();
    auto result =
        P4ParserDriver::parseProgramSources(preprocessorResult.value().get(), options.file.c_str());

    if (::P4::errorCount() > 0) {
        ::P4::error(ErrorType::ERR_OVERLIMIT, "%1% errors encountered, aborting compilation",
                    ::P4::errorCount());
        return std::nullopt;
    }

    BUG_CHECK(result.first != nullptr, "Parsing failed, but no error was reported");

    return result;
}


int getFeatures(P4LACPPOptions& options, const IR::P4Program *program){
    auto extractor = P4FeatureExtractor();
    program->apply(extractor);

    std::string featuresInJson = extractor.toJSON();
    if (featuresInJson.empty()) {
        return EXIT_FAILURE;
    };

    std::ostream *out = nullptr;
    // Write to stdout in absence of an output file.
    if (options.getFeatureOutFile().empty()) {
        out = &std::cout;
    } else {
        out = openFile(options.getFeatureOutFile(), false);
        if ((out == nullptr) || !(*out)) {
            ::P4::error(ErrorType::ERR_NOT_FOUND, "%2%: No such file or directory.",
                        options.getFeatureOutFile().string());
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

int dumpAfterFrontend(P4LACPPOptions& options, const IR::P4Program *program){
    if (!options.getDumpOptimizedFile().empty()) {
        DumpOptimized dumpOptimized(options);
        program->apply(dumpOptimized);
    }
    return EXIT_SUCCESS;
}
}
