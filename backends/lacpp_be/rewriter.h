#ifndef BACKENDS_REWRITER_H_
#define BACKENDS_REWRITER_H_

#include "ir/ir.h"
#include "ir/visitor.h"

#include <vector>
#include <unordered_map>
#include <optional>

namespace P4::P4LACPP{

class Rewriter : public PassManager{
public:
   explicit Rewriter(){
        setName("Rewriter");
        addPasses({
            new TableMerge(),
        });
    }
};

class TableMerge : public Transform{

public:
 TableMerge(){
    setName("TableMerge");
 }

 Visitor::profile_t init_apply(const IR::Node *node) override;
 void end_apply(const IR::Node *) override;
 const IR::Node *postorder(IR::P4Control *control) override;

private:
 const cstring first_tbl = "tbl_set_b"_cs;
 const cstring second_tbl = "tbl_set_b_w_c"_cs;
 const cstring merged_tbl = "tbl_merged"_cs;

 const IR::P4Table * mergeTwoTables(const IR::P4Table *first, const IR::P4Table *second);

};

};


#endif /* BACKENDS_REWRITER_H_ */