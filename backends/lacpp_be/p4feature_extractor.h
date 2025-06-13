#ifndef BACKENDS_P4FEATURE_EXTRACTOR_H_
#define BACKENDS_P4FEATURE_EXTRACTOR_H_

#include "ir/ir.h"
#include "ir/visitor.h"

#include <vector>
#include <unordered_map>
#include <optional>

namespace P4::P4LACPP{

// frontend also has a TypeMap, I defined this for simplicity
// it is a tree structure: struct/header -> fields : types
struct FieldTypeSizeInfo{
    cstring field_name;
    cstring type;
    uint32_t size = 0;
    FieldTypeSizeInfo(cstring f_name, cstring type_name , uint32_t s)
        : field_name(f_name), type(type_name), size(s) {}
    FieldTypeSizeInfo() = default;
    FieldTypeSizeInfo(const FieldTypeSizeInfo &other)
        : field_name(other.field_name), type(other.type), size(other.size) {}

    cstring toString() const {
        return field_name + " : " + type + " : " + std::to_string(size);
    }
};

// field name: FieldTypeSizeInfo
typedef std::unordered_map<cstring, FieldTypeSizeInfo> FieldSizeMap;
// struct name: map of field name to FieldTypeSizeInfo
typedef std::unordered_map<cstring, FieldSizeMap> StructFieldMap;
class TypeMap{
public:
    TypeMap() = default;
    // struct name: map of field name to type and size
    StructFieldMap struct_fields;
    StructFieldMap header_fields;

    void addStructField(cstring struct_name, cstring field_name, cstring type, uint32_t size = 0) {
        struct_fields[struct_name][field_name] = FieldTypeSizeInfo(field_name, type, size);
    }
    void addHeaderField(cstring header_name, cstring field_name, cstring type, uint32_t size = 0) {
        header_fields[header_name][field_name] = FieldTypeSizeInfo(field_name, type, size);
    }

    bool hasStruct(cstring struct_name) {
        return struct_fields.find(struct_name) != struct_fields.end();
    }
    bool hasHeader(cstring header_name) {
        return header_fields.find(header_name) != header_fields.end();
    }

    void dump() const {
        LOG1("TypeMap dump:");
        for (const auto &[struct_name, fields] : struct_fields) {
            LOG1("Struct: " << struct_name);
            for (const auto &[field_name, info] : fields) {
                LOG1("  " << info.toString());
            }
        }
        for (const auto &[header_name, fields] : header_fields) {
            LOG1("Header: " << header_name);
            for (const auto &[field_name, info] : fields) {
                LOG1("  " << info.toString());
            }
        }
    }


};

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
    // local decls
    std::unordered_map<cstring, cstring> field_to_type;

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
 // for match key size collection
 bool preorder(const IR::Type_Struct *c) override;
 bool preorder(const IR::Type_Header *c) override;

 // params of controls, not go for actions for now
//  bool preorder(const IR::ParameterList *p) override;
//  bool preorder(const IR::TableProperties *t) override;
////  TBD: currently no need to implement:
//  bool preorder(const IR::TypeParameters *p) override;


//  bool preorder(const IR::Method *p) override;
//  bool preorder(const IR::Function *function) override;

//  bool preorder(const IR::ActionListElement *ale) override;
// bool preorder(const IR::ActionList *v) override;
// bool preorder(const IR::Key *v) override;
// bool preorder(const IR::Property *p) override;

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
    TypeMap type_map;


    // helpers
    void init_action_info(cstring new_action_name);
    void end_action_info();
    void init_table_info(cstring new_table_name);
    void end_table_info();
};



};


#endif /* BACKENDS_P4FEATURE_EXTRACTOR_H_ */