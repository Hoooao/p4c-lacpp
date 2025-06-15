#include "backends/lacpp_be/p4feature_extractor.h"
#include "thrid_party/json.hpp"

#include <list>

namespace P4::P4LACPP{

using FE=P4FeatureExtractor;
using json=nlohmann::ordered_json;


std::optional<FieldSizeMap> TypeMap::getFieldSizeMap(cstring name) const {
    if (hasStruct(name)) {
        return struct_fields.at(name);
    }else if (hasHeader(name)) {
        return header_fields.at(name);
    } else if (hasField(name)) {
        return fields;
    }
    return std::nullopt; // Not found
}

Visitor::profile_t FE::init_apply(const IR::Node *node){
    LOG1("Feature extraction init_apply");
    return Inspector::init_apply(node);
}

void FE::end_apply(const IR::Node *) {
    // check log level
    if(LOGGING(2)){
        type_map.dump();   
    }
    LOG1("Feature extraction end_apply");
}

// for now care only tables..
bool FE::preorder(const IR::Node *n){
   LOG1("Skipped Node: " << n->toString().c_str());
   return false;
}

bool FE::preorder(const IR::P4Program *program){
    for (auto a : program->objects) {
        if(a->is<IR::P4Control>() || a->is<IR::Type_Struct>() || 
           a->is<IR::Type_Header>() || a->is<IR::Type_Typedef>()){
            visit(a);
        }
    }
    return false;
}
bool FE::preorder(const IR::P4Control *c){
    const IR::Type_Control * tc = c->type->to<IR::Type_Control>();
    LOG1("In Control Block: " << tc->name.toString());
    if(tc->name.toString() == "ingress"){
        curGress = GressTypes::INGRESS;
        gresses.insert({GressTypes::INGRESS, {GressTypes::INGRESS}});
    }else if(tc->name.toString() == "egress"){// it is actually SwitchEgress in smith
        curGress = GressTypes::EGRESS;
        gresses.insert({GressTypes::EGRESS, {GressTypes::EGRESS}});
    }else return false; // do not traverse other control blocks for now!

    auto params = c->type->to<IR::Type_Control>()->applyParams;
    auto& gress = gresses.at(curGress);
    if(params != nullptr) {
        LOG2("Parameters: ");
        for(const auto &param : params->parameters) {
            LOG2("   " << param->name.toString() << " type: " << param->type->toString());
            if(param->type->is<IR::Type_Bits>()){
                gress.addField(param->name.toString(),
                param->type->toString(), param->type->to<IR::Type_Bits>()->size);
            }else{
                gress.addField(param->name.toString(), param->type->toString());
            }
        }
    }

    auto decls = c->controlLocals;
    if(decls.size() > 0) {
        LOG2("Declarations: ");
        for(const auto &decl : decls) {
            if(decl->is<IR::Declaration_Variable>()) {
                auto var = decl->to<IR::Declaration_Variable>();
                LOG2("   " << var->name.toString() << " type: " << var->type->toString());
                if(var->type->is<IR::Type_Bits>()){
                    gress.addField(var->name.toString(),
                    var->type->toString(), var->type->to<IR::Type_Bits>()->size);
                }else{
                    gress.addField(var->name.toString(), var->type->toString());
                }
            }
        }
    }
    return true;
}

bool FE::preorder(const IR::P4Action *c){
    const auto &name = c->name.toString();
    LOG1("In Action: " << name);
    init_action_info(name);
    // TODO(Hao): extract param? get the number of ops not loc. 
    // only count the number of statOrDeclt for now.. 
    curAct.value().op_num = c->body->components.size();
    LOG2("Op num:" << curAct.value().op_num);
    end_action_info();
    return false;
}


std::list<cstring> FE::get_components(const IR::Expression *expr) {
    std::list<cstring> components;
    // e.g. hdr.ipv4.dstAddr:
    //  hdr is PathExpression, ipv4 and dstAddr are Member,
    //  organized in {Member{Member{PathExpr}}}
    while(expr){
        if (auto path = expr->to<IR::PathExpression>()) {
            components.push_front(path->path->name.toString());
            break;
        }else if (auto member = expr->to<IR::Member>()) {
            components.push_front(member->member.toString());
            expr = member->expr;
        } else if(auto ar = expr->to<IR::ArrayIndex>()){
            // stacks like hdr.ipv4[0].dstAddr, not quite sure this
            // is actually used in manual progs..
            // perhaps I should remove this in smith as well?
            expr = ar->left;
        }else{
            // i am not supporting Constant anymore in smith..
            BUG("Unknown expression type in key element: %1%", expr->node_type_name());
        }
    }
    return components;
}
uint32_t FE::resolve_non_stack_field_size(cstring field) {
    // return field from type_map(including typedefs) or local decls
    // Note: the "field" can also be a typedef name!
    auto gress_decls = gresses.at(curGress).field_decls;
    auto global_decls = type_map.fields;
    while(true){
        auto gress_it = gress_decls.find(field);

        if(gress_it != gress_decls.end()){
            auto &info = gress_it->second;
            if(info.size > 0 || info.type == "bit<0>") {
                return info.size;
            }
        }else{
            auto global_it = global_decls.find(field);
            if(global_it != global_decls.end()){
                auto &info = global_it->second;
                if(info.size > 0 || info.type == "bit<0>") {
                    return info.size;
                }
                field = info.type;
            }else{
                BUG("Field %1% not found in gress or global decls", field);
            }
        }
    }
    return 0; // should not reach here
}

uint32_t FE::resolve_stack_field_size(std::list<cstring> &components){
    cstring stack_var = components.front();
    components.pop_front();
    auto& gress = gresses.at(curGress);
    // root stack type
    cstring type = gress.field_decls.at(stack_var).type;
    
    while(!components.empty()){
        // Note: the last field can be a non-stack type,
        //  so we have getFieldSizeMap also check the non-stack field map
        auto fsm = type_map.getFieldSizeMap(type);
        if(fsm == std::nullopt){
            BUG("Field size map not found for stack type: %1%", type);
        }
        cstring field = components.front();
        components.pop_front();
        auto ele = fsm->find(field);
        if(ele == fsm->end()){
            type_map.dump();
            BUG("Field %1% not found in stack type %2%", field, type);
        }
        FieldTypeSizeInfo &info = ele->second;
        if(info.size > 0 || info.type == "bit<0>") { //bit<0> is used for padding
            // found the size
            return info.size;
        } else {
            // not found, continue to next level
            type = info.type;
        }           
    }
    return resolve_non_stack_field_size(type); // last field can be non-stack type
} 

uint32_t FE::resolve_key_ele_size(const IR::KeyElement *key) {
    std::list<cstring> components = get_components(key->expression);
    // non-stack types
    if(components.size() == 1) {
        return resolve_non_stack_field_size(components.front());
    }
    return resolve_stack_field_size(components);
    
    return 0;
}

bool FE::preorder(const IR::P4Table *c){
    const auto &name = c->name.toString();
    LOG1("In Table: " << name);
    init_table_info(name);

    auto &acts = curTable.value().actions;
    auto &matches = curTable.value().matches;

    // TODO(Hao): Properties: key, action, size, entries
    const auto actList = c->getActionList();
    if(actList != nullptr) {
        LOG2("ActionList: ");
        for(const auto ele: actList->actionList){
            LOG2("   " << ele->toString());
            acts.emplace_back(ele->toString());
        }
    }
    const auto keys = c->getKey();
    if(keys!=nullptr){
        LOG2("Keys: ");
        for(const auto ele: keys->keyElements){
            cstring type = ele->matchType->toString();
            cstring key = ele->expression->toString();
            uint32_t size = resolve_key_ele_size(ele);
            LOG2("   " << key <<" matchType: " << type << " size: " << size);
            if(type == "exact") matches[MatchTypes::EXACT].push_back(std::make_pair(key,size));
            else if(type == "ternary") matches[MatchTypes::TERNARY].push_back(std::make_pair(key,size));
            else if(type == "lpm") matches[MatchTypes::LPM].push_back(std::make_pair(key,size));
            else BUG("Unknown match type");
        }
    }
    auto sizePtr = c->getSizeProperty();
    // Default size is 512 in tofino
    curTable.value().size = sizePtr == nullptr ? 512 : sizePtr->asUnsigned();
    end_table_info();
    return false;
}


bool FE::preorder(const IR::Type_Struct *c){
    // print name and size and return
    auto fields = c->fields;
    LOG1("In Struct: " << c->name.toString());
    if(type_map.hasStruct(c->name.toString())){
        BUG("    Type already exists in type map: %1%", c->name.toString());
        return false; // already processed
    }
    
    for(auto f: fields){
        auto type = f->type;
        if(type->is<IR::Type_Name>()){
            LOG1("    Field: "<< f->name.toString() << " type: " << type->toString());
            type_map.addStructField(c->name.toString(), f->name.toString(), type->toString());
        }else if(type->is<IR::Type_Stack>()){
            type = type->to<IR::Type_Stack>()->elementType;
            LOG1("    Field: "<< f->name.toString() << " stack type: " << type->toString());
            type_map.addStructField(c->name.toString(), f->name.toString(), type->toString());
        }else{
            LOG1("    Field: "<< f->name.toString() << " size: " << f->type->width_bits());
            // add to type map
            type_map.addStructField(c->name.toString(), f->name.toString(), type->toString(), f->type->width_bits());
        }
       
    }
    return false;
}

bool FE::preorder(const IR::Type_Header *c){
    // iterate through the fields and print name and size
    auto fields = c->fields;
    int width_bits = 0;
    LOG1("In Header: " << c->name.toString());
    for(auto f: fields){
        auto type = f->type;
        if(type->is<IR::Type_Name>()){
            LOG1("    Field: "<< f->name.toString() << " type: " << type->toString());
            type_map.addHeaderField(c->name.toString(), f->name.toString(), type->toString());
        }else if(type->is<IR::Type_Stack>()){
            type = type->to<IR::Type_Stack>()->elementType;
            LOG1("    Field: "<< f->name.toString() << " stack type: " << type->toString());
            type_map.addHeaderField(c->name.toString(), f->name.toString(), type->toString());
        }else{
            LOG1("    Field: "<< f->name.toString() << " size: " << f->type->width_bits());
            width_bits = f->type->width_bits();
        }
        type_map.addHeaderField(c->name.toString(), f->name.toString(), type->toString(), width_bits);
    }
    return false;
}

bool FE::preorder(const IR::Type_Typedef *c){
    // e.g. typedef DigestType_t bit<32>;
    // just add to the field map
    LOG1("In Typedef: " << c->name.toString() << " type: " << c->type->toString());
    if(c->type->is<IR::Type_Bits>()){
        type_map.addField(c->name.toString(), c->type->toString(), c->type->width_bits());
    }else if(c->type->is<IR::Type_Name>()){
        // resolve the size here if it is a typedef of a bit<>
        auto info_it = type_map.fields.find(c->type->toString());
        if(info_it == type_map.fields.end()){
            type_map.addField(c->name.toString(), c->type->toString());
        }else{
            type_map.addField(c->name.toString(), info_it->second.type, info_it->second.size); 
        }
    }else{
        BUG("Unknown typedef type: %1%", c->type->node_type_name());
    }
    return false;
}

// TBD: currently no need to implement:

// bool FE::preorder(const IR::TypeParameters *p){}


// bool FE::preorder(const IR::Method *p){}
// bool FE::preorder(const IR::Function *function){}


//// These are table related stuff, not needed as prcossed all in P4Table
// bool FE::preorder(const IR::ActionListElement *ale){}
// bool FE::preorder(const IR::ActionList *v){}
// bool FE::preorder(const IR::Key *v){}
// bool FE::preorder(const IR::Property *p){}
// bool FE::preorder(const IR::TableProperties *t){}
// bool FE::preorder(const IR::EntriesList *l){}
// bool FE::preorder(const IR::Entry *e){}

// bool FE::preorder(const IR::Operation *op){
//     //TODO(Hao): add op in action, or some block..
//     // retun true for nested ones.
//     return true;
// }

// Helpers
void FE::init_action_info(cstring name){
    BUG_CHECK(curGress!=GressTypes::NONE, "action should appear in a control block of a gress");
    BUG_CHECK(!curAct.has_value(), "There exists initialized action");
    auto &acts = gresses.at(curGress).actions;
    BUG_CHECK(acts.find(name) == acts.end(), "duplicate action name %s in control", name.c_str());
    curAct = name;
}

void FE::end_action_info(){
    BUG_CHECK(curAct.has_value(), "No action initialized");
    auto &acts = gresses.at(curGress).actions;
    acts[curAct.value().name] = curAct.value();
    curAct.reset();
}

void FE::init_table_info(cstring name){
    BUG_CHECK(curGress!=GressTypes::NONE, "tables should appear in a control block of a gress");
    BUG_CHECK(!curTable.has_value(), "There exists initialized table");
    auto &tables = gresses.at(curGress).tables;
    BUG_CHECK(tables.find(name) == tables.end(), "duplicate action name %s in control", name.c_str());
    curTable = name;
}

void FE::end_table_info(){
    BUG_CHECK(curTable.has_value(), "No table initialized");
    auto &tables = gresses.at(curGress).tables;
    tables[curTable.value().name] = curTable.value();
    curTable.reset();
}   



// TO JSONS
inline void to_json(json& j, const cstring& s) {j = s.c_str();}
void to_json(json& j, const MatchTypes& m) {
    switch (m) {
        case MatchTypes::EXACT: j = "exact"; break;
        case MatchTypes::LPM: j = "lpm"; break;
        case MatchTypes::TERNARY: j = "ternary"; break;
    }
}

void to_json(json& j, const GressTypes& g) {
    switch (g) {
        case GressTypes::INGRESS: j = "ingress"; break;
        case GressTypes::EGRESS: j = "egress"; break;
        case GressTypes::NONE: j = "ternary"; break;
    }
}
std::string to_string(const GressTypes& g) {
    switch (g) {
        case GressTypes::INGRESS: return "ingress"; 
        case GressTypes::EGRESS: return "egress";
        case GressTypes::NONE: return "ternary"; 
    }
    return {};
}

void to_json(json& j, const actionInfo& a) {
    j = json{{"name", a.name}, {"op_num", a.op_num}};
}

void to_json(json& j, const tableInfo& t) {
    j = json{
        {"name", t.name},
        {"size", t.size},
        {"actions", t.actions},
        {"matches", t.matches}
    };
}

void to_json(json& j, const GressInfo& g) {
    json json_tables = json::object();
    json json_actions = json::object();
    for(auto &[k,v]: g.tables){
        json_tables[k.c_str()] = v;
    }
    for(auto &[k,v]: g.actions){
        json_actions[k.c_str()] = v;
    }
    j = json{
        {"type", g.type},
        {"actions", json_actions},
        {"tables", json_tables}
    };
}

std::string FE::toJSON(){
    json j = json::object();
    for(auto& [k,v]: gresses) j[to_string(k)] = v;
    return j.dump(2);
}
}