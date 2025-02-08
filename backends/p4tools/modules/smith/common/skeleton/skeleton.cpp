#include "skeleton.h"

namespace TableDepSkeleton
{
    TableDepSkeleton::TableDepSkeleton(Matrix matrix){
        adjMatrix = matrix;
        uint32_t dim = matrix.size();
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
        // find table with no inbound edges
        for(auto table : tables){
            if(table->inboundEdges.size() == 0){
                zeroIndegreeTables.push_back(table);
            }
        }
    }
} // namespace TableDepSkeleton
