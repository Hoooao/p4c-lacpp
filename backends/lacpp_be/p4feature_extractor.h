#ifndef BACKENDS_P4FEATURE_EXTRACTOR_H_
#define BACKENDS_P4FEATURE_EXTRACTOR_H_

#include "ir/ir.h"
#include "ir/visitor.h"

#include <vector>
#include <unordered_map>
#include <optional>

namespace P4::P4LACPP{

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

// field name to FieldTypeSizeInfo
typedef std::unordered_map<cstring, FieldTypeSizeInfo> FieldSizeMap;
// struct name to map of field name to FieldTypeSizeInfo
typedef std::unordered_map<cstring, FieldSizeMap> StructFieldMap;

// frontend also has a TypeMap, I defined this for simplicity
class TypeMap{
public:
    TypeMap() = default;
    // struct name: map of field name to type and size
    StructFieldMap struct_fields;
    StructFieldMap header_fields;
    FieldSizeMap fields;

    void addStructField(cstring struct_name, cstring field_name, cstring type, uint32_t size = 0) {
        struct_fields[struct_name].emplace(field_name, FieldTypeSizeInfo(field_name, type, size));
    }
    void addHeaderField(cstring header_name, cstring field_name, cstring type, uint32_t size = 0) {
        header_fields[header_name].emplace(field_name, FieldTypeSizeInfo(field_name, type, size));
    }

    void addField(cstring field_name, cstring type, uint32_t size = 0) {
        fields.emplace(field_name, FieldTypeSizeInfo(field_name, type, size));
    }

    bool hasStruct(cstring struct_name) const {
        return struct_fields.find(struct_name) != struct_fields.end();
    }
    bool hasHeader(cstring header_name) const {
        return header_fields.find(header_name) != header_fields.end();
    }
    bool hasField(cstring field_name) const {
        return fields.find(field_name) != fields.end();
    }

    std::optional<FieldSizeMap> getFieldSizeMap(cstring struct_name) const;


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
        for (const auto &[field_name, info] : fields) {
            LOG1("Field: " << info.toString());
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
    std::vector<uint32_t> params_sizes;
    actionInfo() = default;
    actionInfo(cstring n_name):name(n_name), op_num(0){};
};

struct tableInfo{
    cstring name;
    uint32_t size;
    std::vector<cstring> actions;
    std::unordered_map<MatchTypes,std::vector<std::pair<cstring, uint32_t> >> matches;

    tableInfo() = default;
    tableInfo(cstring n_name):name(n_name), size(0){};
};

struct GressInfo{
    GressTypes type;
    std::unordered_map<cstring, actionInfo> actions;
    std::unordered_map<cstring, tableInfo> tables;
    // local decls
    FieldSizeMap field_decls;

    GressInfo(GressTypes t):type(t){};
    void addField(cstring field_name, cstring type, uint32_t size = 0) {
        field_decls.emplace(field_name, FieldTypeSizeInfo(field_name, type, size));
    }
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
 bool preorder(const IR::Type_Typedef *c) override;

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
    std::list<cstring> get_components(const IR::Expression *expr);
    // structish means struct and header
    uint32_t resolve_non_strutish_field_size(cstring field);
    uint32_t resolve_strutish_field_size(std::list<cstring> &components);
    uint32_t resolve_key_ele_size(const IR::KeyElement *key);
};

};


#endif /* BACKENDS_P4FEATURE_EXTRACTOR_H_ */