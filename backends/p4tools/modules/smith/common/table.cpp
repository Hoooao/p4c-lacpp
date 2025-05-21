#include "backends/p4tools/modules/smith/common/table.h"

#include <cstddef>
#include <cstdio>
#include <set>
#include <utility>

#include "backends/p4tools/common/lib/logging.h"
#include "backends/p4tools/common/lib/util.h"
#include "backends/p4tools/modules/smith/common/declarations.h"
#include "backends/p4tools/modules/smith/common/expressions.h"
#include "backends/p4tools/modules/smith/common/probabilities.h"
#include "backends/p4tools/modules/smith/common/scope.h"
#include "backends/p4tools/modules/smith/core/target.h"
#include "backends/p4tools/modules/smith/util/util.h"
#include "ir/indexed_vector.h"
#include "ir/vector.h"
#include "lib/cstring.h"
#include "lib/exceptions.h"


namespace P4::P4Tools::P4Smith {

IR::P4Table *TableGenerator::genTableDeclaration() {
    IR::TableProperties *tbProperties = genTablePropertyList();
    cstring name = getRandomString(6);
    auto *ret = new IR::P4Table(name, tbProperties);
    P4Scope::addToScope(ret);
    // Hao: ask fabian why it is, wierd stuff, cause compiling to fail
    // P4Scope::callableTables.emplace(ret);
    return ret;
}

IR::TableProperties *TableGenerator::genTablePropertyList() {
    IR::IndexedVector<IR::Property> tabProperties;

    tabProperties.push_back(genKeyProperty());
    tabProperties.push_back(genActionListProperty());
    tabProperties.push_back(genSizeProperty());

    return new IR::TableProperties(tabProperties);
}

IR::Key *TableGenerator::genKeyElementList(size_t len) {
    IR::Vector<IR::KeyElement> keys;
    bool enforce = Utils::getRandInt({
        Probabilities::get().TABLE_DEPENDENCY_ENFORCE,
        Probabilities::get().TABLE_DEPENDENCY_NOT_ENFORCE
    });
    if(enforce==0 && SmithOptions::get().enableDagGeneration && TableDepSkeleton::TableDepSkeleton::getSkeleton()!=nullptr){
        const auto tn = TableDepSkeleton::TableDepSkeleton::getSkeleton()->currentNode;
        for(const auto &fields: tn->parentsWritten){
            // choose one fields to match, sufficient for dependancy
            if(fields.size() == 0) continue;
            const auto field = fields.at(Utils::getRandInt(0, fields.size() - 1));
            auto *key = genKeyElement(field->expression);
            tn->fieldsMatched.push_back(field);
            keys.push_back(key);
            break;
        }
    }

    for (size_t i = keys.size(); i < len; i++) {
        IR::KeyElement *key = genKeyElement();
        if (key == nullptr) {
            continue;
        }
        // @name
        // Tao: actually, this may never happen
        const auto *keyAnno = key->getAnnotations().at(0);
        const auto *annotExpr = keyAnno->getExpr(0);
        cstring keyAnnotatName;
        if (annotExpr->is<IR::StringLiteral>()) {
            const auto *strExpr = annotExpr->to<IR::StringLiteral>();
            keyAnnotatName = strExpr->value;
        } else {
            BUG("must be a string literal");
        }

        keys.push_back(key);
    }

    return new IR::Key(keys);
}


cstring TableGenerator::genKeyMatchType() {
    std::string match_kind;
    std::vector<int64_t> typePercent = {
        Probabilities::get().TABLEDECLARATION_MATCH_EXACT,
        Probabilities::get().TABLEDECLARATION_MATCH_LPM,
        Probabilities::get().TABLEDECLARATION_MATCH_TERNARY,
    };
    auto rand = Utils::getRandInt(typePercent);
    if(rand == 0){
        match_kind = "exact";
    }else if(rand == 1 && !P4Scope::prop.lpm_used && !P4Scope::prop.ternary_used){
        match_kind = "lpm";
    }else if(rand == 2 && !P4Scope::prop.lpm_used){
        // there can be multiple ternary matches
        match_kind = "ternary";
    }else{
        match_kind = "exact";
    }
    return match_kind;
}

IR::KeyElement *TableGenerator::genKeyElement() {
    cstring match_type = genKeyMatchType();
    auto *match = new IR::PathExpression(std::move(IR::ID(match_type)));
    auto annotations = target().declarationGenerator().genAnnotation();
    auto *bitType = P4Scope::pickDeclaredBitType(false);

    // Ideally this should have a fallback option
    if (bitType == nullptr) {
        printInfo("Could not find key lval for key matches\n");
        return nullptr;
    }
    // this expression can!be an infinite precision integer
    P4Scope::req.require_scalar = true;
    // no func call in key
    P4Scope::constraints.method_call_max_in_stat = 0;
    auto *expr = target().expressionGenerator().genExpression(bitType);
    printInfo("genKeyElement: expr:%s", expr->toString().c_str());
    P4Scope::constraints.method_call_max_in_stat = 1;
    P4Scope::req.require_scalar = false;
    if (match_type == "lpm") {
        P4Scope::prop.lpm_used = true;
    }else if (match_type == "ternary") {
        P4Scope::prop.ternary_used = true;
    }
    auto *key = new IR::KeyElement(expr, match, annotations);

    return key;
}

IR::KeyElement *TableGenerator::genKeyElement(const IR::Expression* expr) {
    cstring match_type = genKeyMatchType();
    if (match_type == "lpm") {
        P4Scope::prop.lpm_used = true;
    } else if (match_type == "ternary") {
        P4Scope::prop.ternary_used = true;
    }
    auto *match = new IR::PathExpression(std::move(IR::ID(match_type)));
    auto annotations = target().declarationGenerator().genAnnotation();
    auto *key = new IR::KeyElement(expr, match, annotations);
    return key;
}

IR::Property *TableGenerator::genKeyProperty() {
    cstring name = IR::TableProperties::keyPropertyName;
    auto *keys = genKeyElementList(Utils::getRandInt(0, 5));
    P4Scope::prop.lpm_used = false;
    P4Scope::prop.ternary_used = false;
    // isConstant --> false
    return new IR::Property(name, keys, false);
}

IR::Property *TableGenerator::genSizeProperty(){
    std::vector<int64_t> typePercent = {
        Probabilities::get().TABLEDECLARATION_SIZE_512,
        Probabilities::get().TABLEDECLARATION_SIZE_1024,
        Probabilities::get().TABLEDECLARATION_SIZE_2048,
        Probabilities::get().TABLEDECLARATION_SIZE_4096,
        Probabilities::get().TABLEDECLARATION_SIZE_8192,
        Probabilities::get().TABLEDECLARATION_SIZE_16384,
        Probabilities::get().TABLEDECLARATION_SIZE_32768,
        Probabilities::get().TABLEDECLARATION_SIZE_65536
    };
    uint64_t size = 512 * pow(2, Utils::getRandInt(typePercent));

    return new IR::Property(
        IR::TableProperties::sizePropertyName,
        new IR::ExpressionValue(new IR::Constant(size)),  // 32 bits
        false);
}

IR::MethodCallExpression *TableGenerator::genTableActionCall(cstring method_name,
                                                             const IR::ParameterList &params) {
    auto *args = new IR::Vector<IR::Argument>();
    IR::IndexedVector<IR::StatOrDecl> decls;

    for (const auto *par : params) {
        if (!target().expressionGenerator().checkInputArg(par)) {
            return nullptr;
        }
        if (par->direction == IR::Direction::None) {
            // do nothing; in tables directionless parameters are
            // set by the control plane
            continue;
        }
        IR::Argument *arg = nullptr;
        if (par->direction == IR::Direction::In) {
            // the generated expression needs to be compile-time known
            P4Scope::req.compile_time_known = true;
            arg = new IR::Argument(target().expressionGenerator().genExpression(par->type));
            P4Scope::req.compile_time_known = false;
        } else {
            arg = new IR::Argument(target().expressionGenerator().pickLvalOrSlice(par->type));
        }
        args->push_back(arg);
    }
    auto *pathExpr = new IR::PathExpression(method_name);
    return new IR::MethodCallExpression(pathExpr, args);
}

IR::ActionList *TableGenerator::genActionList(size_t len) {
    IR::IndexedVector<IR::ActionListElement> actList;
    std::set<cstring> actNames;

    // prioritize the actions need to be used for dependancy generation
    if(SmithOptions::get().enableDagGeneration && TableDepSkeleton::TableDepSkeleton::getSkeleton()!=nullptr){
        const auto tn = TableDepSkeleton::TableDepSkeleton::getSkeleton()->currentNode;
        for(const auto action : tn->actionsToUse){
            const auto *act = action->to<IR::P4Action>();
            actNames.insert(act->name.name);
            const auto *params = act->parameters;
            IR::MethodCallExpression *mce = genTableActionCall(act->name.name, *params);
            if (mce != nullptr) {
                auto *actlistEle = new IR::ActionListElement(mce);
                actList.push_back(actlistEle);
            }
        }
    }


    auto p4Actions = P4Scope::getDecls<IR::P4Action>();

    if (p4Actions.empty()) {
        return new IR::ActionList(actList);
    }
    
    for (size_t i = actList.size(); i < len; i++) {
        if(p4Actions.size()==0) continue;
        size_t idx = Utils::getRandInt(0, p4Actions.size() - 1);
        const auto *p4Act = p4Actions[idx];
        cstring actName = p4Act->name.name;

        if (actNames.find(actName) != actNames.end()) {
            continue;
        }
        actNames.insert(actName);

        const auto *params = p4Act->parameters;

        IR::MethodCallExpression *mce = genTableActionCall(actName, *params);
        if (mce != nullptr) {
            auto *actlistEle = new IR::ActionListElement(mce);
            actList.push_back(actlistEle);
        }
    }
    return new IR::ActionList(actList);
}

IR::Property *TableGenerator::genActionListProperty() {
    cstring name = IR::TableProperties::actionsPropertyName;
    auto *acts = genActionList(Utils::getRandInt(0, 3));

    return new IR::Property(name, acts, false);
}

}  // namespace P4::P4Tools::P4Smith
