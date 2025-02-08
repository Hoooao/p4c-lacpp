#ifndef SKELETON_H
#define SKELETON_H
#include "adjacencyMatGen.h"
#include <iostream>
#include <memory>

typedef std::vector<std::vector<uint32_t>> Matrix;

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
        std::vector<std::shared_ptr<Dependency>> outboundEdges;
        std::vector<std::shared_ptr<Dependency>> inboundEdges;

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
        std::vector<std::shared_ptr<TableNode>> tables;
        std::vector<std::shared_ptr<Dependency>> dependencies;

        // probably where to start traversing
        std::vector<std::shared_ptr<TableNode>> zeroIndegreeTables;

        TableDepSkeleton(Matrix adjMatrix);
    };


    // helper functions

} // namespace TableDepSkeleton

#endif // SKELETON_HPP