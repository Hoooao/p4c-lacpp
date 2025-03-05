#include "skeleton.h"


namespace TableDepSkeleton
{
    void TableNode::extractFieldsWrittenInBlock(IR::BlockStatement *blk){
            for (const auto *stmt : blk->components) {
            if (const auto *assign = stmt->to<IR::AssignmentStatement>()) {
                // check if the lval is in the scope
                if (P4Tools::P4Smith::P4Scope::hasLval(assign->left)) {
                    const auto *left = assign->left;
                    cstring lvalStr = nullptr;
                    if (const auto *path = left->to<IR::PathExpression>()) {
                        lvalStr = path->path->name.name;
                    } else if (const auto *mem = left->to<IR::Member>()) {
                        lvalStr = mem->member.name;
                    } else if (const auto *slice = left->to<IR::AbstractSlice>()) {
                        lvalStr = slice->e0->to<IR::PathExpression>()->path->name.name;
                    } else if (const auto *arrIdx = left->to<IR::ArrayIndex>()) {
                        lvalStr = arrIdx->left->to<IR::PathExpression>()->path->name.name;
                    }

                    IR::NamedExpression *ne = new IR::NamedExpression(left->srcInfo, lvalStr,left);
                    // check if ne is already in the fieldsWritten
                    // only add once, otherwise the vector class will complain with error
                    if (fieldsWritten.getDeclaration(lvalStr) == nullptr) {
                        fieldsWritten.push_back(ne);
                        P4Tools::printInfo("Var used in action %s: %s", name.c_str(), lvalStr.c_str());
                    }
                }
            }
        }
    }
    TableDepSkeleton::TableDepSkeleton(Matrix matrix):adjMatrix(matrix), currentNode(nullptr){
        uint32_t dim = matrix.size();
        std::vector<std::shared_ptr<TableNode>> tables;
        for (uint32_t i = 0; i < dim; ++i) {
            tables.push_back(std::make_shared<TableNode>());
            // TODO rand gen the name later
            tables[i]->name = "table" + std::to_string(i);
        }
        for(uint32_t i = 0; i < dim; i++){
            for(uint32_t j=0;j<i;j++){
                for( uint32_t k = 0; k < matrix[i][j]; k++){
                    std::shared_ptr<Dependency> dep = std::make_shared<Dependency>();
                    // the source is always the table with the higher index in the matrix to make a DAG
                    dep->source = tables[i];
                    dep->target = tables[j];
                    dep->type = DependencyType::RAW;
                    dependencies.push_back(dep);
                    tables[i]->outboundEdges.push_back(dep);
                    tables[j]->inboundEdges.push_back(dep);
                }
            }
        }
        // find table with no inbound edges to start with
        for(auto table : tables){
            if(table->inboundEdges.size() == 0){
                tableNodeQueue.push(table);
            }else{
                tNode2InboundNum[table] = table->inboundEdges.size();
            }
        }
    }

    void TableDepSkeleton::updateInboundNumForOutboundAndTryEnqueue(std::shared_ptr<TableNode> table){
        for(auto dep : table->outboundEdges){
            tNode2InboundNum[dep->target] -= 1;
            if(tNode2InboundNum[dep->target] == 0){
                P4Tools::printInfo("Table %s has no more inbound edges, enqueued", dep->target->name.c_str());
                tableNodeQueue.push(dep->target);
                tNode2InboundNum.erase(dep->target);
            }
        }
    }

    void TableDepSkeleton::pupolateTableApplyToBlock(IR::BlockStatement *blk){
        for(auto table : tablesInOrder){
            auto *expr =
                new IR::MethodCallExpression(new IR::Member(new IR::PathExpression(table->table->name), "apply"));
            blk->components.push_back(new IR::MethodCallStatement(expr));
        }
    }
} // namespace TableDepSkeleton
