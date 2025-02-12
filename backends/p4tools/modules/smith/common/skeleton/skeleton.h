#ifndef SKELETON_H
#define SKELETON_H
#include "adjacencyMatGen.h"
#include "ir/ir.h"
#include "ir/indexed_vector.h"
#include "backends/p4tools/modules/smith/common/scope.h"
#include "backends/p4tools/common/lib/logging.h"
#include <iostream>
#include <memory>
#include <queue>

typedef std::vector<std::vector<uint32_t>> Matrix;
using namespace P4;
namespace TableDepSkeleton
{
    class Dependency;

    enum class DependencyType
    {
        // TODO: clarify these types..
        // For now just focus on read after write, seems easy to implement
        //  requirement: the 1st table write a field, the 2nd table match the field
        // could be optimized by frontend, but does not matter..
        // But we implement FLOW first, which means no dependency besides sequential order
        WAW,
        RAW,
        WAR,
        FLOW
    };

    class TableNode{
    public:
        std::string name;
        IR::P4Table * table;
        std::vector<std::shared_ptr<Dependency>> outboundEdges;
        std::vector<std::shared_ptr<Dependency>> inboundEdges;

        // keep track of the fields get matched, get used as right value (skip for now), get written as left value
        IR::IndexedVector<IR::NamedExpression> fieldsMatched; // keys
        IR::IndexedVector<IR::NamedExpression> fieldsWritten; // l value

        std::vector<IR::IndexedVector<IR::NamedExpression>> parentsMatched; 
        std::vector<IR::IndexedVector<IR::NamedExpression>> parentsWritten;

        // Actions to use, need to cast to IR::Action
        IR::IndexedVector<IR::Declaration> actionsToUse;


        void extractFieldsWrittenInBlock(IR::BlockStatement *blk);

    };
    class Dependency{
    public:
        std::shared_ptr<TableNode> source;
        std::shared_ptr<TableNode> target;
        DependencyType type;
    };

    class TableDepSkeleton{
    public:
        Matrix adjMatrix;

        std::shared_ptr<TableNode> currentNode;
        // The order that gets applied
        std::vector<std::shared_ptr<TableNode>> tablesInOrder;
        std::vector<std::shared_ptr<Dependency>> dependencies;
        // BFS: process only the tables with no inbound edges
        std::unordered_map<std::shared_ptr<TableNode>, uint32_t> tNode2InboundNum;
        std::queue<std::shared_ptr<TableNode>> tableNodeQueue;

        static std::shared_ptr<TableDepSkeleton>& getSkeleton(){
            static std::shared_ptr<TableDepSkeleton> instance;
            return instance;
        }
        TableDepSkeleton(Matrix adjMatrix);

        // Add to BFS queue if no more inbound edges
        // Called each time after a node is instantiated.
        void updateInboundNumForOutboundAndTryEnqueue(std::shared_ptr<TableNode> table);

        void pupolateTableApplyToBlock(IR::BlockStatement *blk);
    
    };


} // namespace TableDepSkeleton

#endif // SKELETON_HPP