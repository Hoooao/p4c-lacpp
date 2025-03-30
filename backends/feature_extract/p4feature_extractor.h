#ifndef BACKENDS_P4FEATURE_EXTRACTOR_H_
#define BACKENDS_P4FEATURE_EXTRACTOR_H_

#include "ir/ir.h"
#include "ir/visitor.h"

#include <vector>
#include <unordered_map>
#include <optional>

namespace P4::P4Features{


enum class MatchTypes{
    EXACT,
    TERNARY,
    LPM
};

enum class GressTypes{
    INGRESS,
    EGRESS,
    NONE
};

struct actionInfo{
    cstring name;
    uint32_t op_num;
    actionInfo() = default;
    actionInfo(cstring n_name):name(n_name), op_num(0){};
};

struct tableInfo{
    cstring name;
    uint32_t size;
    std::vector<cstring> actions;
    std::unordered_map<MatchTypes,std::vector<cstring>> matches;

    tableInfo() = default;
    tableInfo(cstring n_name):name(n_name), size(0){};
};

struct GressInfo{
    GressTypes type;
    std::unordered_map<cstring, actionInfo> actions;
    std::unordered_map<cstring, tableInfo> tables;

    GressInfo(GressTypes t):type(t){};
};


class P4FeatureExtractor : public Inspector{

public:
 P4FeatureExtractor(){
    setName("P4FeatureExtractor");
 }

 using Inspector::preorder;

 Visitor::profile_t init_apply(const IR::Node *node) override;

 void end_apply(const IR::Node *node) override;
 // for now care only tables..
 bool preorder(const IR::Node *n) override;
 bool preorder(const IR::P4Program *program) override;
 bool preorder(const IR::P4Control *c) override;
 bool preorder(const IR::P4Action *c) override;
 bool preorder(const IR::P4Table *c) override;

////  TBD: currently no need to implement:
//  bool preorder(const IR::TypeParameters *p) override;
//  bool preorder(const IR::ParameterList *p) override;

//  bool preorder(const IR::Method *p) override;
//  bool preorder(const IR::Function *function) override;

//  bool preorder(const IR::ActionListElement *ale) override;
// bool preorder(const IR::ActionList *v) override;
// bool preorder(const IR::Key *v) override;
// bool preorder(const IR::Property *p) override;
// bool preorder(const IR::TableProperties *t) override;
// bool preorder(const IR::EntriesList *l) override;
// bool preorder(const IR::Entry *e) override;

// bool preorder(const IR::Operation *op) override;
 // Assuming cstring is std::string-compatible (if not, adapt accordingly)
std::string toJSON();

private:
    std::unordered_map<GressTypes, GressInfo> gresses; 
    GressTypes curGress = GressTypes::NONE;
    std::optional<actionInfo> curAct = std::nullopt;
    std::optional<tableInfo> curTable = std::nullopt;


    // helpers
    void init_action_info(cstring new_action_name);
    void end_action_info();
    void init_table_info(cstring new_table_name);
    void end_table_info();
};
};


#endif /* BACKENDS_P4FEATURE_EXTRACTOR_H_ */