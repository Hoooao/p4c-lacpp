#include "backends/lacpp_be/p4feature_extractor.h"
#include "thrid_party/json.hpp"

namespace P4::P4LACPP{

using FE=P4FeatureExtractor;
using json=nlohmann::ordered_json;

Visitor::profile_t FE::init_apply(const IR::Node *node){
    LOG1("Feature extraction init_apply");
    return Inspector::init_apply(node);
}

void FE::end_apply(const IR::Node *) {
    type_map.dump();
    LOG1("Feature extraction end_apply");
}

// for now care only tables..
bool FE::preorder(const IR::Node *n){
   LOG1("Skipped Node: " << n->toString().c_str());
   return false;
}

bool FE::preorder(const IR::P4Program *program){
    for (auto a : program->objects) {
        // and global bit fields??
        if(a->is<IR::P4Control>() || a->is<IR::Type_Struct>() || a->is<IR::Type_Header>()){
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
    if(params != nullptr) {
        LOG2("Parameters: ");
        for(const auto &param : params->parameters) {
            LOG2("   " << param->name.toString() << " type: " << param->type->toString());
            gresses[curGress].field_to_type[param->name.toString()] = param->type->toString();
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
            LOG2("   " << key <<" matchType: " << type);
            if(type == "exact") matches[MatchTypes::EXACT].push_back(key);
            else if(type == "ternary") matches[MatchTypes::TERNARY].push_back(key);
            else if(type == "lpm") matches[MatchTypes::LPM].push_back(key);
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
        }else if(type->is<IR::Type_Stack>()){
            type = type->to<IR::Type_Stack>()->elementType;
            LOG1("    Field: "<< f->name.toString() << " stack type: " << type->toString());
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
    //LOG1("In Header: " << c->name.toString() << " size: " << c->width_bits());
    LOG1("In Header: " << c->name.toString());
    for(auto f: fields){
        auto type = f->type;
        if(type->is<IR::Type_Name>()){
            LOG1("    Field: "<< f->name.toString() << " type: " << type->toString());
        }else if(type->is<IR::Type_Stack>()){
            type = type->to<IR::Type_Stack>()->elementType;
            LOG1("    Field: "<< f->name.toString() << " stack type: " << type->toString() <<
                 " size: " << f->type->width_bits());
            width_bits = f->type->width_bits();
        }else{
            LOG1("    Field: "<< f->name.toString() << " size: " << f->type->width_bits());
            width_bits = f->type->width_bits();
        }
        type_map.addHeaderField(c->name.toString(), f->name.toString(), type->toString(), width_bits);
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