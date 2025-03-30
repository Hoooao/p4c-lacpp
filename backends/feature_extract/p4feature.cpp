#include "frontends/common/options.h"
#include "frontends/common/parseInput.h"
#include "frontends/common/parser_options.h"
#include "frontends/parsers/parserDriver.h"
#include "frontends/p4/frontend.h"
#include "ir/ir.h"

#include "backends/feature_extract/p4feature.h"
#include "backends/feature_extract/p4feature_extractor.h"


namespace P4::P4Features{
std::optional<std::pair<const IR::P4Program *, const Util::InputSources *>> parseProgram(
    const ParserOptions &options) {
    if (!std::filesystem::exists(options.file)) {
        ::P4::error(ErrorType::ERR_NOT_FOUND, "%1%: No such file found.", options.file);
        return std::nullopt;
    }
    if (options.isv1()) {
        ::P4::error(ErrorType::ERR_UNKNOWN, "p4fmt cannot deal with p4-14 programs.");
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


std::string getFeatures(std::filesystem::path inputFile){
    AutoCompileContext autoP4FeaturesContext(new P4FeaturesContext);
    auto &options = P4FeaturesContext::get().options();
    options.file = std::move(inputFile);

    auto parseResult = parseProgram(options);
    if (!parseResult) {
        if (::P4::errorCount() > 0) {
            ::P4::error("Failed to parse P4 file.");
        }
        return {};
    }
    const auto &[program, _] = *parseResult;
    auto extractor = P4FeatureExtractor();
    program->apply(extractor);

    return extractor.toJSON();
}
}
