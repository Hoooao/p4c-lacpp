#include "backends/lacpp_be/rewriter.h"
#include "thrid_party/json.hpp"
#include "frontends/p4/toP4/toP4.h"
#include "lib/nullstream.h"
#include <list>
#include <fstream>

namespace P4::P4LACPP{

Visitor::profile_t TableMerge::init_apply(const IR::Node *node){
    LOG1("TableMerge init_apply");
    return Transform::init_apply(node);
}

void TableMerge::end_apply(const IR::Node *n) {
    LOG1("TableMerge end_apply");
    // std::filesystem::path output_file = "rewrit.p4";
    // std::filesystem::path a = "waw.rewrit.p4";
    // std::ostream *ppStream = openFile(output_file, true);
    // P4::ToP4 top4(ppStream, false, a);
    // (void)n->apply(top4);
    Transform::end_apply(n);
}

const IR::P4Table *TableMerge::mergeTwoTables(const IR::P4Table *first, const IR::P4Table *second){
    LOG1("Merging tables: " << first->name.toString() << " and " << second->name.toString());
    // Create a new table that merges the two tables
    // Merge keys
    IR::Vector<IR::KeyElement> newKeys;
    for (auto k : first->getKey()->keyElements) {
        newKeys.push_back(k);
    }
    // for (auto k : second->getKey()->keyElements) {
    //     newKeys.push_back(k);
    // }
    auto newKeyProp = new IR::Property(
            IR::TableProperties::keyPropertyName,
            new IR::Key(newKeys),
        false);

    // Merge sizes
    // should be multiplication..
    uint32_t new_size = std::stoul(first->getSizeProperty()->to<IR::Constant>()->toString().c_str()) + std::stoul(second->getSizeProperty()->to<IR::Constant>()->toString().c_str());
    auto new_size_property = new IR::Property(
            IR::TableProperties::sizePropertyName,
            new IR::ExpressionValue(new IR::Constant(new_size)),  // 32 bits
        false);

    // Merge action lists
    IR::IndexedVector<IR::ActionListElement> newActions;
    for (auto a : first->getActionList()->actionList) {
        newActions.push_back(a);
    }
    for (auto a : second->getActionList()->actionList) {
        newActions.push_back(a);
    }
    auto newActionProp = new IR::Property(
            IR::TableProperties::actionsPropertyName,
            new IR::ActionList(newActions),
        false);
    
    IR::IndexedVector<IR::Property> newProperties;
    
    newProperties.push_back(newKeyProp);
    newProperties.push_back(newActionProp);
    newProperties.push_back(new_size_property);
    cstring name = "tbl_merged"_cs;
    auto newTable = new IR::P4Table(name, new IR::TableProperties(newProperties));
    LOG1("Created merged table: " << newTable->name.toString());
    return newTable;
}


// Hardcode for WAW for now
const IR::Node *TableMerge::postorder(IR::P4Control *c) {
    //return NULL;
    LOG1("In Control Block: " << c->name.toString());
    auto decls = c->controlLocals;
    std::vector<const IR::P4Table *> tables;
    if(decls.size() > 0) {
        LOG2("Declarations: ");
        for(const auto &decl : decls) {
            if(decl->is<IR::P4Table>()) {
                auto tbl = decl->to<IR::P4Table>();
                tables.push_back(tbl);
                LOG2("Table: " << tbl->name.toString());
            }
        }
        if(tables.size() == 2) {
            mergeTwoTables(tables[0], tables[1]);
            // Remove the second table from the control locals
            decls.erase(std::remove(decls.begin(), decls.end(), tables[1]), decls.end());
            // Replace the first table with the merged table
            decls.erase(std::remove(decls.begin(), decls.end(), tables[0]), decls.end());
            auto mergedTable = mergeTwoTables(tables[0], tables[1]);
            decls.push_back(mergedTable);
            c->controlLocals = decls;
            LOG1("Rewrote control block: " << c->name.toString());

            auto *mem = new IR::Member(new IR::PathExpression(mergedTable->name), "apply");
            auto *mce = new IR::MethodCallExpression(mem);
            auto *mcs = new IR::MethodCallStatement(mce);
            P4::IR::IndexedVector<P4::IR::StatOrDecl> newStats;
            newStats.push_back(mcs);
            c->body = new IR::BlockStatement(newStats);
        }
    }
    return c;
}

}