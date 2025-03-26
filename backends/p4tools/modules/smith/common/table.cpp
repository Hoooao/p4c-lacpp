#include "backends/p4tools/modules/smith/common/table.h"

#include <cstddef>
#include <cstdio>
#include <set>
#include <utility>

#include "backends/p4tools/common/lib/logging.h"
#include "backends/p4tools/common/lib/util.h"
#include "backends/p4tools/modules/smith/common/declarations.h"
#include "backends/p4tools/modules/smith/common/expressions.h"
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

    return new IR::TableProperties(tabProperties);
}

IR::Key *TableGenerator::genKeyElementList(size_t len) {
    IR::Vector<IR::KeyElement> keys;
    if(SmithOptions::get().enableDagGeneration && TableDepSkeleton::TableDepSkeleton::getSkeleton()!=nullptr){
        const auto tn = TableDepSkeleton::TableDepSkeleton::getSkeleton()->currentNode;
        for(const auto &fields: tn->parentsWritten){
            // choose one fields to match, sufficient for dependancy
            if(fields.size() == 0) continue;
            const auto field = fields.at(Utils::getRandInt(0, fields.size() - 1));
            auto *key = genKeyElement("exact", field->expression);
            tn->fieldsMatched.push_back(field);
            keys.push_back(key);
        }
    }

    for (size_t i = keys.size(); i < len; i++) {
        // TODO(fruffy): More types than just exact
        IR::KeyElement *key = genKeyElement("exact");
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

IR::KeyElement *TableGenerator::genKeyElement(IR::ID match_kind) {
    auto *match = new IR::PathExpression(std::move(match_kind));
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
    P4Scope::constraints.method_call_max_in_stat = 1;
    P4Scope::req.require_scalar = false;


    auto *key = new IR::KeyElement(expr, match, annotations);

    return key;
}

IR::KeyElement *TableGenerator::genKeyElement(IR::ID match_kind, const IR::Expression* expr) {
    auto *match = new IR::PathExpression(std::move(match_kind));
    auto annotations = target().declarationGenerator().genAnnotation();
    auto *key = new IR::KeyElement(expr, match, annotations);
    return key;
}

IR::Property *TableGenerator::genKeyProperty() {
    cstring name = IR::TableProperties::keyPropertyName;
    auto *keys = genKeyElementList(Utils::getRandInt(0, 3));

    // isConstant --> false
    return new IR::Property(name, keys, false);
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
